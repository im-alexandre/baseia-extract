"""Keep MinerU uploads off the Network Volume and force durable artifacts."""

from __future__ import annotations

import os
import shutil
import tempfile

import persistent_results


def _patch_fast_api() -> None:
    from mineru.cli import fast_api

    if getattr(fast_api, "_baseia_upload_patch", False):
        return
    async def create_async_parse_task(request_options):
        # The server package is always complete regardless of response options.
        request_options.return_md = True
        request_options.return_middle_json = True
        request_options.return_images = True
        request_options.return_content_list = True
        task_id = str(fast_api.uuid.uuid4())
        task_output_dir = fast_api.create_task_output_dir(task_id)
        uploads_dir = tempfile.mkdtemp(prefix=f"mineru-uploads-{task_id}-")
        task_manager = fast_api.get_task_manager()
        try:
            uploads = await fast_api.save_upload_files(
                uploads_dir,
                request_options.files,
            )
            request_options.files.clear()
            task = fast_api.AsyncParseTask(
                task_id=task_id,
                status=fast_api.TASK_PENDING,
                backend=request_options.backend,
                file_names=[upload.stem for upload in uploads],
                created_at=fast_api.utc_now_iso(),
                output_dir=task_output_dir,
                effort=request_options.effort,
                parse_method=request_options.parse_method,
                lang_list=request_options.lang_list,
                formula_enable=request_options.formula_enable,
                table_enable=request_options.table_enable,
                image_analysis=request_options.image_analysis,
                server_url=request_options.server_url,
                return_md=request_options.return_md,
                return_middle_json=request_options.return_middle_json,
                return_model_output=request_options.return_model_output,
                return_content_list=request_options.return_content_list,
                return_images=request_options.return_images,
                response_format_zip=request_options.response_format_zip,
                return_original_file=request_options.return_original_file,
                client_side_output_generation=request_options.client_side_output_generation,
                start_page_id=request_options.start_page_id,
                end_page_id=request_options.end_page_id,
                upload_names=[upload.original_name for upload in uploads],
                uploads=[upload.path for upload in uploads],
            )
            await task_manager.submit(task)
            return task
        except fast_api.HTTPException:
            fast_api.cleanup_file(task_output_dir)
            shutil.rmtree(uploads_dir, ignore_errors=True)
            raise
        except Exception:
            fast_api.cleanup_file(task_output_dir)
            shutil.rmtree(uploads_dir, ignore_errors=True)
            raise

    original_run_task = fast_api.AsyncTaskManager._run_task

    async def run_task(self, task):
        try:
            await original_run_task(self, task)
            if task.status == fast_api.TASK_COMPLETED:
                persistent_results.record_worker_completion(task)
        finally:
            if task.uploads:
                shutil.rmtree(os.path.dirname(task.uploads[0]), ignore_errors=True)

    fast_api.create_async_parse_task = create_async_parse_task
    fast_api.AsyncTaskManager._run_task = run_task
    fast_api._baseia_upload_patch = True


try:
    _patch_fast_api()
except Exception:
    # The module is also imported by build-time utilities where MinerU may not
    # yet be installed; the runtime entrypoint validates the required version.
    pass
