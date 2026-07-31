from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .reporting import reporter
from .settings import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _control_root() -> Path:
    context_id = os.getenv("BASEIA_CONTEXT_ID", "").strip()
    project_key = hashlib.sha256(
        (
            str(settings.project_root).casefold()
            + "\0"
            + context_id.casefold()
        ).encode("utf-8")
    ).hexdigest()[:12]
    return (
        Path(tempfile.gettempdir())
        / "baseia-extract"
        / project_key
    )


def _current_state_path() -> Path:
    return _control_root() / "current.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _pid_alive(pid: object) -> bool:
    try:
        numeric_pid = int(str(pid))
    except (TypeError, ValueError):
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        open_process = kernel32.OpenProcess
        open_process.argtypes = [
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        open_process.restype = ctypes.c_void_p
        handle = open_process(
            process_query_limited_information,
            False,
            numeric_pid,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong),
            ]
            if not get_exit_code(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle(handle)

    try:
        os.kill(numeric_pid, 0)
    except OSError:
        return False
    return True


def _active_state() -> dict[str, Any] | None:
    state = _read_json(_current_state_path())
    if state is None or not _pid_alive(state.get("pid")):
        return None
    return state


def normalize_api_urls(
    api_urls: tuple[str, ...],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_url in api_urls:
        url = raw_url.strip().rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Endpoint MinerU inválido: {raw_url!r}. "
                "Informe uma URL HTTP(S), não um ID de pod."
            )
        if parsed.query or parsed.fragment:
            raise ValueError(
                f"Endpoint MinerU não pode conter query ou fragmento: {url}"
            )
        normalized.append(url)
    return tuple(dict.fromkeys(normalized))


def _queue_stop(state: dict[str, Any]) -> Path:
    command_dir = Path(str(state["command_dir"]))
    command_path = (
        command_dir
        / f"{time.time_ns()}-{uuid.uuid4().hex}.json"
    )
    _write_json(
        command_path,
        {
            "created_at": _now(),
            "action": "stop",
        },
    )
    return command_path


def start(
    api_urls: tuple[str, ...] = (),
    workers: int = 3,
    sample: bool = False,
) -> dict[str, Any]:
    active = _active_state()
    if active is not None:
        if active.get("status") == "stopping":
            raise RuntimeError(
                "A extração está drenando e não aceita novos endpoints."
            )
        if api_urls:
            raise RuntimeError(
                "A extração oficial MinerU já fixou seu endpoint e a "
                "concorrência anunciada por GET /health. Aguarde o término "
                "para selecionar outro endpoint."
            )
        print(
            f"Extração já está ativa: pid={active['pid']}\n"
            f"Log: {active['log_path']}",
            flush=True,
        )
        return active

    if workers < 0:
        raise ValueError("--workers não pode ser negativo.")
    initial_api_urls = normalize_api_urls(
        api_urls or (settings.mineru_api_url,)
    )

    run_id = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    ) + f"-{uuid.uuid4().hex[:8]}"
    run_dir = _control_root() / "runs" / run_id
    command_dir = run_dir / "commands"
    log_path = run_dir / "extract.log"
    command_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "run_id": run_id,
        "pid": os.getpid(),
        "status": "running",
        "scope": "sample" if sample else "inventory",
        "started_at": _now(),
        "run_dir": str(run_dir),
        "command_dir": str(command_dir),
        "log_path": str(log_path),
    }
    _write_json(run_dir / "state.json", state)
    _write_json(_current_state_path(), state)

    reporter.configure(log_path)
    reporter.event(
        f"Extração em primeiro plano | pid={state['pid']} | "
        f"run={run_id}",
        color="cyan",
    )
    reporter.event(f"Log temporário: {log_path}", color="dim")

    try:
        from .tasks import run_extract

        result = run_extract(
            api_urls=initial_api_urls,
            workers=workers,
            sample=sample,
            command_dir=command_dir,
            run_id=run_id,
        )
        state["status"] = (
            "stopped"
            if result["extraction"].get("stopped_early")
            else "complete"
        )
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        state["error"] = "Interrompida pelo terminal."
        reporter.event(
            "Extração interrompida pelo terminal.",
            level="WARNING",
            color="yellow",
        )
    except Exception as error:
        state["status"] = "failed"
        state["error"] = f"{type(error).__name__}: {error}"
        reporter.event(
            f"Falha na extração: {state['error']}",
            level="ERROR",
            color="red",
        )
        raise
    finally:
        state["finished_at"] = _now()
        _write_json(run_dir / "state.json", state)
        _write_json(_current_state_path(), state)
        reporter.event(
            f"Extração finalizada | status={state['status']}",
            color=(
                "green"
                if state["status"] == "complete"
                else "yellow"
            ),
        )
        reporter.close()

    return state


def stop() -> dict[str, Any]:
    state = _active_state()
    if state is None:
        raise RuntimeError("Nenhuma extração ativa.")
    command_path = _queue_stop(state)
    state["status"] = "stopping"
    state["stop_requested_at"] = _now()
    _write_json(Path(str(state["run_dir"])) / "state.json", state)
    _write_json(_current_state_path(), state)
    print(
        "Encerramento gracioso solicitado. A execução não enviará "
        "novos documentos e aguardará os que estão em voo.\n"
        f"Comando: {command_path}",
        flush=True,
    )
    return state


def status() -> dict[str, Any] | None:
    state = _read_json(_current_state_path())
    if state is None:
        print("Nenhuma execução registrada.", flush=True)
        return None
    state = {
        **state,
        "process_alive": _pid_alive(state.get("pid")),
    }
    print(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        flush=True,
    )
    return state


def show_log(lines: int = 80) -> dict[str, Any] | None:
    state = _read_json(_current_state_path())
    if state is None:
        print("Nenhuma execução registrada.", flush=True)
        return None

    log_path = Path(str(state["log_path"]))
    if not log_path.exists():
        print(f"Log ainda não criado: {log_path}", flush=True)
        return state

    content = log_path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()
    print("\n".join(content[-lines:]), flush=True)
    print(
        f"\nLog: {log_path}\n"
        f"Acompanhar: Get-Content -LiteralPath '{log_path}' -Wait",
        flush=True,
    )
    return state


_LOG_FIELD = re.compile(r"(?P<key>[a-zA-Z0-9_]+)=(?P<value>\S+)")


def _log_fields(message: str) -> dict[str, str]:
    return {
        match.group("key"): match.group("value")
        for match in _LOG_FIELD.finditer(message)
    }


def _average_and_max(value: str | None) -> str:
    if not value or value == "-":
        return "-"
    values = [
        int(item.removesuffix("%"))
        for item in value.split("/")
        if item.removesuffix("%").isdigit()
    ]
    if not values:
        return "-"
    return f"{sum(values) / len(values):.0f}%/{max(values)}%"


def _watch_render(
    summary: dict[str, str],
    pods: dict[str, dict[str, str]],
    *,
    process_alive: bool,
    run_status: str,
    updated_at: str,
) -> Group:
    work = Table(title="Trabalho", expand=True)
    work.add_column("Endpoint", style="cyan", no_wrap=True)
    work.add_column("Estado/Circuito", no_wrap=True)
    work.add_column("Cliente/API", justify="right", no_wrap=True)
    work.add_column("Voo/Ocioso", justify="right", no_wrap=True)
    work.add_column("OK/R/E", justify="right", no_wrap=True)
    work.add_column("Fila", justify="right")
    work.add_column("Pág/min · p95", justify="right", style="green", no_wrap=True)

    pressure = Table(title="Pressão", expand=True)
    pressure.add_column("Endpoint", style="cyan", no_wrap=True)
    pressure.add_column("GPU média/máx", justify="right", no_wrap=True)
    pressure.add_column("VRAM média/máx", justify="right", no_wrap=True)
    pressure.add_column("CPU", justify="right")
    pressure.add_column("RAM", justify="right")

    for label, pod in pods.items():
        work.add_row(
            label,
            f"{pod.get('saude', '-')}/{pod.get('circuito', '-')}",
            f"{pod.get('cliente', '-')}/{pod.get('api', '-')}",
            f"{pod.get('em_voo', '-')}/{pod.get('ocioso', '-')}",
            f"{pod.get('concluidos', '-')}/{pod.get('retries', '-')}/"
            f"{pod.get('erros', '-')}",
            pod.get("fila_api", "-"),
            f"{pod.get('paginas_min', '-')} · {pod.get('p95_s', '-')}",
        )
        pressure.add_row(
            label,
            _average_and_max(pod.get("gpu")),
            _average_and_max(pod.get("vram")),
            pod.get("cpu", "-"),
            pod.get("ram", "-"),
        )

    if not pods:
        work.add_row("aguardando", "-", "-/-", "-/-", "-/-/-", "-", "- · -")
        pressure.add_row("aguardando", "-", "-", "-", "-")

    state = (
        "ENCERRANDO"
        if run_status == "stopping"
        else "EXECUTANDO"
        if process_alive
        else run_status.upper()
    )
    details = "\n".join(
        (
            f"[bold]{state}[/bold]  total={summary.get('total', '-')}  "
            f"[green]concluídos={summary.get('concluidos', '-')}[/green]  "
            f"reutilizados={summary.get('reutilizados', '-')}  "
            f"pendentes={summary.get('pendentes', '-')}",
            f"em voo={summary.get('em_voo', '-')}  "
            f"[yellow]retries={summary.get('retries', '-')}[/yellow]  "
            f"[red]erros={summary.get('erros', '-')}[/red]  "
            f"endpoints={summary.get('endpoints', '-')}  "
            f"capacidade={summary.get('capacidade', '-')}  "
            f"ociosa={summary.get('ociosa', '-')}",
            f"[green]vazão={summary.get('paginas_min', '-')} pág/min[/green]  "
            f"média={summary.get('paginas_min_media', '-')} pág/min  "
            f"{summary.get('docs_min', '-')} docs/min  "
            f"[dim]atualizado={updated_at or '-'}[/dim]",
        )
    )
    return Group(work, pressure, Panel(details, title="Extração MinerU"))


def watch_dashboard(refresh_seconds: float = 1.0) -> dict[str, Any] | None:
    """Acompanha somente o quadro agregado da extração ativa."""
    state = _read_json(_current_state_path())
    if state is None:
        print("Nenhuma execução registrada.", flush=True)
        return None

    log_path = Path(str(state["log_path"]))
    summary: dict[str, str] = {}
    pods: dict[str, dict[str, str]] = {}
    updated_at = ""
    offset = 0

    def consume() -> None:
        nonlocal offset, pods, summary, updated_at
        if not log_path.exists():
            return
        with log_path.open("r", encoding="utf-8", errors="replace") as stream:
            stream.seek(offset)
            for line in stream:
                message = line.split("] ", 1)[-1].strip()
                if message.startswith("estado "):
                    summary = _log_fields(message)
                    pods = {}
                    updated_at = line[:23]
                elif message.startswith("endpoint="):
                    fields = _log_fields(message)
                    label = fields.get("endpoint")
                    if label:
                        pods[label] = fields
            offset = stream.tell()

    consume()
    interval = max(0.25, refresh_seconds)
    try:
        with Live(
            _watch_render(
                summary,
                pods,
                process_alive=_pid_alive(state.get("pid")),
                run_status=str(state.get("status", "unknown")),
                updated_at=updated_at,
            ),
            refresh_per_second=max(1, int(1 / interval)),
            screen=True,
        ) as live:
            while True:
                consume()
                current = _read_json(_current_state_path()) or state
                alive = _pid_alive(current.get("pid"))
                live.update(
                    _watch_render(
                        summary,
                        pods,
                        process_alive=alive,
                        run_status=str(current.get("status", "unknown")),
                        updated_at=updated_at,
                    ),
                    refresh=True,
                )
                if not alive:
                    break
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    return state


def dispatch(
    action: str,
    api_urls: tuple[str, ...],
    workers: int = 3,
    sample: bool = False,
) -> dict[str, Any] | None:
    normalized_action = action.strip().casefold()
    if normalized_action == "start":
        return start(api_urls, workers, sample)
    if sample:
        raise ValueError("--sample só pode ser usado com a ação start.")
    if normalized_action == "status":
        return status()
    if normalized_action == "log":
        return show_log()
    if normalized_action == "watch":
        return watch_dashboard()
    if normalized_action == "stop":
        return stop()
    raise ValueError(
        f"Ação inválida: {action!r}. "
        "Use start, stop, status, log ou watch."
    )
