Applied Financial Economics, 1996, 6, 543Ð549

K.-G. L im

Portfolio hedging and basis risks

K.-G. L im

Portfolio hedging and basis risks

K.-G. L im

Portfolio hedging and basis risks

This article was downloaded by: [University of Western Cape]
On: 26 November 2012, At: 00:31
Publisher: Routledge
Informa Ltd Registered in England and Wales Registered Number: 1072954 Registered office:
Mortimer House, 37-41 Mortimer Street, London W1T 3JH, UK

![](<../../mineru/documents/035ca90614af2355/035ca90614af235551917e2fa5297d091092bf8b79eea6a8581ad84d55be0904/auto/images/720b75fff704bd70463344f12e9900601af3ebb32b96aa0bfdfd8e07b09bd53c.jpg>)

## Applied Financial Economics

Publication details, including instructions for authors and subscription
information:
http://www.tandfonline.com/loi/rafe20

## Portfolio hedging and basis risks

Kian-Guan Lim

Version of record first published: 06 Oct 2010.

To cite this article: Kian-Guan Lim (1996): Portfolio hedging and basis risks, Applied Financial Economics, 6:6,
543-549

To link to this article: http://dx.doi.org/10.1080/096031096334006

## PLEASE SCROLL DOWN FOR ARTICLE

## Full terms and conditions of use: http://www.tandfonline.com/page/terms-and-conditions

This article may be used for research, teaching, and private study purposes. Any substantial
or systematic reproduction, redistribution, reselling, loan, sub-licensing, systematic supply, or
distribution in any form to anyone is expressly forbidden.

The publisher does not give any warranty express or implied or make any representation that the
contents will be complete or accurate or up to date. The accuracy of any instructions, formulae, and
drug doses should be independently verified with primary sources. The publisher shall not be liable
for any loss, actions, claims, proceedings, demand, or costs or damages whatsoever or howsoever
caused arising directly or indirectly in connection with or arising out of the use of this material.

# Portfolio hedging and basis risks

KIAN-GUAN LIM

Department of Finance and Banking, Faculty of Business Administration, National
University of Singapore, 10 Kent Ridge Crescent, Singapore 0511

Minimum variance hedged portfolios using futures are formed by taking the linear
projection of spot price changes onto futures price movements as the hedge ratio. This
unwittingly assumes that the underlying spotÐfutures price movements follow a coin-
tegrated process, given that the spot and the futures prices are integrated processes. If
the spotÐfutures prices are not cointegrated, the hedged portfolio suers from the risk
of potentially large changes in its value. Empirical ®ndings using the Nikkei stock
index and the Nikkei 225 futures show this deviation in intraday trading prices. The
basis movements which have often been used by intraday traders to predict future
price changes, are tested to be mostly unit root processes. This is shown to be due
largely to non-cointegratio n of the spotÐfutures prices, and suggests why it is pro®t-
able to trade futures using basis knowledge only if trading is done on a continual
basis.

## I. INTRODUCTION

Hedgers of price risks in ®nancial assets have to determine
the amount of futures contract to buy or sell to insure
against equity portfolio risks. Obviously the optimal
amount depends on the hedger’s risk preference (Stulz, 1984;
Figlewski, 1985). More commonly, the minimum variance
hedge ratio is assumed (Ederington, 1979; and Frankcle,
1980), and such hedged portfolios are then examined to see
if ex post risk is minimal. In determining the minimum
variance hedge ratio, spot price changes are linearly projec-
ted onto the futures price changes, and the least squares
estimate of the slope coe cient is used.

I show that, if the spotÐfutures prices are not cointe-
grated, the hedged portfolio su ers from the risk of poten-
tially large changes in its value, which is not well recognized.
Existing studies limit themselves to basis risks; see a thor-
ough study in Figlewski (1984). Basis risk appears to have
been explicitly or implicitly modelled as a discrete station-
ary process. This paper also shows how it is possible that the
basis could also be an integrated process and relates it to the
cointegration econometrics framework developed below.
Empirical testing is performed and implications are then
drawn about hedged portfolio value and basis trading re-
gimes.

I shall ®rstly set up the usual nomenclature for the econo-
metric modelling of spot-futures relationship. Let S denote
the spot price level, F the futures price level, and assume
0960Ð3107 Ó 1996 Routledge

a general linear process

$$
S _ { t } = \alpha + \eta + \beta F _ { t } + \varepsilon _ { t }
$$

where a, g, and$\beta$are constants, t is a time index, e is
a mean-zero residual error and the subscript t indicates
realization in period t. The ®rst dierences in the levels are
related as

$$
\Delta S _ { t } = \gamma + \beta \Delta F _ { t } + \Delta \varepsilon _ { t }
$$

The value change in the minimum variance hedge portfolio
can then be represented by$\Delta S _ { t } - \beta \Delta F _ { t } , \mathrm { o r } \ \gamma + \Delta \varepsilon _ { t }$in each
period t.

Over an interval of time, say n + 1 periods, the cumula-
tive value change is

$$
( n + 1 ) \gamma + \sum _ { t = j } ^ { j + n } \Delta \varepsilon _ { t }
$$

If$\Delta \varepsilon _ { t }$is stationary and independently distributed, the vari-
ance of the cumulative value change increases linearly with
time. The implication is that the hedged portfolio value
follows a random walk. If$\Delta \varepsilon _ { t }$is stationary but serially
correlated, it is possible for the variance of the hedged
portfolio value change to exhibit non-linear patterns over
time.

Finance literature has gathered much empirical evidence
about price levels being unit root processes (Baillie and
Bollerslev, 1989; Corbae and Ouliaris, 1988; Corbae, Lim
and Ouliaris, 1992). Suppose$S _ { t }$and$\boldsymbol { F } _ { t }$are unit root or$I ( 1 )$
processes, then an interesting issue is whether or not$S _ { t }$and
$F _ { t }$are cointegrated with cointegrating vector$( 1 , \ - \beta )$. If
$S _ { t }$and$F _ { t }$are not cointegrated, then$\varepsilon _ { t }$is typically an I(1)
process and$\Delta \varepsilon _ { t }$is stationary though not necessarily inde-
pendently distributed. This leads to the hedged portfolio
value following a random walk.

However, if$S _ { t }$and$F _ { t }$are cointegrated,$\varepsilon _ { t }$is itself station-
ary though not necessarily independent over time. The
hedged portfolio’s cumulative value change can then be
characterized as

$$
( n + 1 ) \gamma + \sum _ { t = j } ^ { j + n } ( \varepsilon _ { t + 1 } - \varepsilon _ { t } )
$$

or$( n + 1 ) \gamma + \varepsilon _ { j + n + 1 } - \varepsilon _ { j }$. Whatever the length of time, i.e.
whatever n may be, the variance or risk of this cumulative
change is constant. Thus the hedged portfolio value will not
deviate with increasing unpredictability over time.

The above arguments show clearly the necessity of per-
forming a cointegrating regression analysis of the spotÐ
futures price levels. This will help determine whether hedged
portfolios are of any use in preserving capital value over any
interval of time. In the following section, I discuss the
cointegration theory and motivate the use of the canonical
cointegrating regression (CCR) technique developed by
Park (1988). Section III reports tests of the unit root hy-
potheses of the spot and futures price levels and the basis for
the Nikkei 225 index and the futures contract. Section IV
contains results of the CCR and also shows a robust result
concerning the I(1) nature of the basis. Apart from implica-
tions on portfolio hedging, the results also have implications
for intraday trading and suggest how past basis movements
could be exploited to yield pro®table information on the
future basis change. Section V contains the conclusions.

## II. COINTEGRATING REGRESSION

This section contains a brief review of cointegration theory
(Engle and Granger, 1987) and relates the theory to the
regression methodology employed in this paper.

A cointegrated regression may be written as

$$
S _ { t } = \omega _ { 1 } \left( \theta _ { 1 } , \mathrm { t } \right) + \beta ^ { \prime } F _ { t } + u _ { t }
$$

where$\omega _ { 1 } \left( \theta _ { 1 } , t \right)$is a deterministic function assumed to de-
pend on time t and is parametrized by$\theta _ { 1 }$. b is an m-vector of
constants and the m-vector process$\boldsymbol { F } _ { t }$evolves according to

$$
F _ { t } = \omega _ { 2 } ( \theta _ { 2 } , t ) + F _ { t - 1 } + \nu _ { t }
$$

where$\mathbf { \omega } _ { \mathbf { \omega } _ { 2 } } ( \theta _ { 2 } , t )$is an m-vector deterministic function. More-
over,$u _ { t }$and$v _ { t }$are random variables of stationary processes.
Therefore,$( S _ { t } { \cal F } _ { t } ^ { \prime } ) ^ { \prime }$is an$( m + 1 )$)-vector integrated order one,
$I ( 1 ) ,$, process. In the spotÐfutures relationship that we are
examining ,$m = 1$

The usual alternative approach to regression involving
these levels is to apply OLS regression involving ®rst dier-
ences. However, the cointegrating regression technique
yields signi®cant advantages over the conventional econo-
metric methodology such as OLS on ®rst dierences.

Stock (1987) and Park and Phillips (1988) have shown
that, when OLS is applied to the cointegrated regression,
the parameter estimates converge to the true parameter b at
the rate$T$(sample size), faster than$\sqrt { T }$for the conven-
tional case. Faster convergence occurs because the sample
moments of the component$\boldsymbol { F } _ { t }$are an order of magnitude
larger than the sample moments of$u _ { t } ,$and this dominates
the impact of any correlation that may exist between the
innovations in$\boldsymbol { F } _ { t }$and the true error term$u _ { t } .$This so-called
superconsistency result continues to hold even in the pres-
ence of contemporaneous correlation in$u _ { t } ,$endogeneity of
$\boldsymbol { F } _ { t }$and stationary measurement error in$S _ { t }$and$\boldsymbol { F } _ { t }$

However, the advantages in favour of OLS disappear if
$S _ { t }$and$\boldsymbol { F } _ { t }$do not form a cointegrated system. Speci®cally,
when$u _ { t }$is itself an integrated process, i.e.$S _ { t }$and$\boldsymbol { F } _ { t }$are not
cointegrated, then applying OLS leads to `spurious’ regres-
sion results (Granger and Newbold, 1974; Phillips, 1986).
In particular, OLS parameter estimates, though unbiased,
are inconsistent when$u _ { t }$is an integrated process, and
the conventional$t -$and F-ratio statistics do not possess
limiting distributions. Also, the DurbinÐWatson statistic
converges in probability to zero, whereas$R ^ { 2 }$has a non-
degenerate limiting distribution as the sample size ap-
proaches in®nity.

I now present an applied methodology, as in Corbae et al.
(1992), for the estimation and testing of cointegrated regres-
sions. Since the existing literature maintains priors of$I ( 1 )$
about the price processes and maintains that spot and
futures prices are cointegrated, I employ test statistics that
use these priors as null hypotheses. This has the eect of
minimal type I error. It also explains why some other
cointegration tests that are based on dierent nulls are not
employed here.

Step 1 Pretest the time-series data$S _ { t }$and$\boldsymbol { F } _ { t }$to determine if
the data are consistent with the I(1) hypothesis. More gener-
ally, a time trend is allowed in the$I ( 1 )$speci®cations. Park
and Choi (1988) suggested a J-statistic for the unit root test
which was shown to have minimum size distortion bias. The
$Z _ { \alpha }$and the$Z _ { t }$statistics (Phillips, 1987) are also used for
comparison. An application of the J-statistic is reported in
Lim and Phoon (1991).

The J-statistic is de®ned as

$$
J ( p , q ) = ( R S S _ { p } - R S S _ { q } ) / R S S _ { q } \qquad { \mathrm { f o r ~ } } 0 < p < q
$$

where$R S S _ { k }$for$k = p , q$is the residual sum of squares from
the regression of$S _ { t }$on a constant,$S _ { t ^ { - } 1 }$, and time variables
$t , \ t ^ { 2 } , \ { \overline { { t } } } ^ { 3 } , \ldots , t ^ { k } .$. Intuitively, this statistic is a test of the
restrictions of the$( p + 1 ) \mathrm { t h }$to qth terms of the time poly-
nomial being zero. If ®tting higher time polynomials is able
to explain variations in$S _ { t } ,$the resulting higher value of the
J-statistic indicates the existence of a unit root.

Step 2 Estimate the coecient b using the canonical coin-
tegrating regression (CCR) technique developed by Park
(1988). Then test whether$S _ { t }$and$\boldsymbol { F } _ { t }$are cointegrated using
Park’s (1988)$H ( p , q ) , q > p ,$statistic. This statistic is based
on a null hypothesis of cointegration, i.e. stationary error,
allowing for deterministic time trend up to the pth order. If
the regression is cointegrated with irrelevant polynomial
time trends, the application of CCR should yield insigni®c-
ant coecients on these variables. The$H ( p , q )$statistic also
possesses an asymptotic$\chi _ { \boldsymbol { q } ^ { - } \boldsymbol { p } } ^ { 2 }$distribution.

The CCR regression technique is based on a GLS-type
correction to the original data; Park (1988) gives the details
of the technique. The transformation is designed to yield an
estimate for b that permits conventional hypothesis testing.
In particular, hypothesis testing may be conducted using
conventional asymptotic$\chi ^ { 2 }$statistics. Park (1988) develops
the CCR procedure under mild regularity conditions for the
innovation sequences driving$S _ { t }$and$\boldsymbol { F } _ { t }$

Moreover, the CCR estimator has the advantage that the
error process is speci®ed in a non-parametri c fashion, and
can easily accommodate deterministic non-stationarity in
$S _ { t }$and$\boldsymbol { F } _ { t }$such as that arising from a constant term and
a time trend.

## III. PRICE PROPERTIES OF THE NIKKEI<br>
INDEX AND FUTURES

Research on the Japanese stock market and the Nikkei 225
futures market has been gaining momentum over the last
several years (Bailey, 1989; Brenner et al., 1989; Lim, 1992a;
Ziemba, 1990). With the wide price swings in the Japanese
stock market, whereby in intraday trades it is common for
the Nikkei 225 index to swing several hundred points either
way, or up to 5% of the total index value, hedging using the
Nikkei 225 stock index futures is a signi®cant activity. The
futures contract was ®rst traded in the Singapore Interna-
tional Monetary Exchange in 1986 and also in the Osaka
Exchange in 1989.

Using intraday futures trading data over 20 days at
5-minute intervals and matching it with the Nikkei 225
index reported at these same intervals, unit root tests were
performed on the time series properties of the index level,
the futures price level and the basis. The 20 trading days
were randomly selected from four contracts: June 1988,
September 1988, June 1989 and September 1989. Each daily
data set comprises time-stamped transaction records show-
ing the traded prices. At each 5-minute interval throughout
the trading day, the traded price just before the end of the
interval was matched with the `QUICK’-reported Nikkei
spot index at the end of the interval.

The computed test statistics are based on the null hy-
potheses of unit roots for the price levels and the basis; they
are the J-statistic developed by Park and Choi (1988), and
the$Z _ { \alpha }$and$Z _ { t }$statistics of Phillips (1987). The empirical
results are reported in Table 1. Statistics that fall below the
critical value indicate rejection of the null at that signi®-
cance level.

Table 1 shows that the futures prices behave as I(1)
process except for day 17 when both the$Z _ { \alpha }$and$Z _ { t }$statistics
indicate rejection of the null at 1% signi®cance. The spot
prices also behave as an$I ( 1 )$process except for days 3 and
12, when the$Z _ { t }$statistics indicate rejection of the null at 1%
signi®cance. The basis appears to follow an I(1) process for
the most part, although it could well be stationary on some
days, e.g. days 4, 9, and 12 when the$Z _ { t }$statistics indicate
rejection of the null at 1% signi®cance. It would appear that
the$Z _ { t }$statistic is more powerful than the$Z _ { \alpha }$and J-statistics,
though Lim and Phoon (1991) discussed the bias towards
rejection in the Z-statistics relative to the J-statistics.

## IV. COINTEGRATION TESTS

In this section, I use the canonical cointegration regression
of Park (1988). The following regression is performed:

$$
\boldsymbol { S } _ { t } = \boldsymbol { \alpha } + \boldsymbol { \gamma } t + \boldsymbol { \beta } \boldsymbol { F } _ { t } + \boldsymbol { \varepsilon } _ { t }
$$

The CCR technique yields consistent estimates of$\alpha , \gamma$and
b provided that$\varepsilon _ { t }$is stationary. Consistency still obtains
even if$\boldsymbol { F } _ { t }$and$\varepsilon _ { t }$are not independent, as this bias reduces to
zero asymptotically. Such desirable features of estimation
using CCR cannot be obtained with OLS regression on the
®rst di erences. As indicated in the previous section, that
$S _ { t }$and$\boldsymbol { F } _ { t }$are typically I(1) processes provides the justi®ca-
tion for applying the CCR technique.

The intraday spot prices are regressed against a constant,
time, and the matched futures prices for each of the 20
trading days. The$H ( p , q )$statistic developed by Park (1988)
to test for deviation from the null of cointegration is com-
puted in each regression. Based on the null of a linear time
trend and ®tting additional time polynomials to degree
3 yields a$\chi ^ { 2 }$distribution with two degrees of freedom for the
H-statistic under the null. The estimates and test statistics
are reported in Table 2.

From the CCR of spot prices on futures prices, the
H-statistics indicate rejection of the null of cointegration for
days 12, 15, 18 and 20 at 1% signi®cance, and for days 1, 3,
6 and 9 at 5% signi®cance. In other words, there are many
days (40% of my sample) in which a hedged portfolio value
behaves like a random walk. In these cases, the portfolios
are unlikely to oer protection against extreme movements
in spot prices.

On the other days, when the null of cointegration is not
rejected, the minimum variance hedge ratios are estimated
to range from about 0.2 to 1.4 with the majority of cases
being close to but below 1. To con®rm this ®nding, an OLS
regression of spot price changes on futures price changes
was also performed. The results are reported in Table 3.

Table 1. Unit root tests of futures prices, spot prices, and basis of the Nikkei 225 contract using the J-statistic and Phillips’ Z-statistics

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Contract | J(1, 5) | Z _ { \alpha } ( 1 , 5 ) | Z{(1, 5) | Contract | J(1, 5) | Z _ { \alpha } ( 1 , 5 ) | Z{(1, 5) |
| June 1988 |  |  |  | June 1989 |  |  |  |
| Trading day 1 |  |  |  | Trading day 11 |  |  |  |
| Futures | 0.956 | -19.065 | - 3.788a | Futures | 0.179 | -19.414 | -3.432 |
| Spot | 6.509 | -7.752 | - 2.058 | Spot | 2.593 | -20.314 | -3.344 |
| Basis | 8.163 | -2.720 | -0.683 | Basis | 2.994 | - 19.235 | -3.131 |
| Trading day 2 |  |  |  | Trading day 12 |  |  |  |
| Futures | 2.926 | -12.000 | - 1.996 | Futures | 0.977 | -14.601 | -2.715 |
| Spot | 0.609 | - 14.320 | - 2.946 | Spot | 2.401 | -23.772 | - 4.948b |
| Basis | 0.604 | -14.043 | -2.760 | Basis | 4.845 | - 18.902 | - 4.707b |
| Trading day 3 |  |  |  | Trading day 13 |  |  |  |
| Futures | 0.254ª | - 21.490ª | - 3.740a | Futures | 4.438 | -5.226 | -1.795 |
| Spot | 2.149 | - 25.163a | - 4.845b | Spot | 5.624 | -4.826 | -1.597 |
| Basis | 3.728 | - 15.451 | -3.438 | Basis | 2.039 | -17.081 | - 3.604a |
| Trading day 4 |  |  |  | Trading day 14 |  |  |  |
| Futures | 1.219 | -8.613 | -2.091 | Futures | 1.361 | -13.803 | -2.965 |
| Spot | 3.141 | - 15.621 | - 4.003a | Spot | 6.388 | - 15.279 | - 3.592a |
| Basis | 8.910 | -18.616 | - 5.389b | Basis | 4.398 | -17.055 | - 3.866a |
| Trading day 5 |  |  |  | Trading day 15 |  |  |  |
| Futures | 6.485 | -2.061 | -0.720 | Futures | 3.252 | -8.862 | - 2.393 |
| Spot | 9.761 | -2.580 | - 0.994 | Spot | 3.153 | -14.781 | - 3.993a |
| Basis | 2.596 | -5.275 | - 1.312 | Basis | 2.361 | -16.615 | -3.607a |
| September 1988 |  |  |  | September 1989 |  |  |  |
| Trading day 6 |  |  |  | Trading day 16 |  |  |  |
| Futures | 1.267 | -10.830 | - 2.823 | Futures | 0.630 | -17.225 | - 3.581a |
| Spot | 1.470 | - 6.940 | -1.464 | Spot | 1.498 | -11.049 | -2.497 |
| Basis | 3.924 | - 14.183 | -3.115 | Basis | 2.762 | -9.055 | - 2.426 |
| Trading day 7 |  |  |  | Trading day 17 |  |  |  |
| Futures | 0.445 | - 21.794a | - 3.758a | Futures | 0.336 | - 30.956b | - 4.895b |
| Spot | 4.766 | -6.428 | - 2.210 | Spot | 0.157a | - 22.538a | - 3.828a |
| Basis | 1.291 | - 13.301 | -3.229 | Basis | 0.148 | - 21.302ª | - 3.926a |
| Trading day 8 |  |  |  | Trading day 18 |  |  |  |
| Futures | 2.240 | -7.386 | -1.443 | Futures | 24.598 | -4.101 | -1.487 |
| Spot | 1.864 | -17.008 | - 3.882a | Spot | 1.363 | -10.051 | -2.569 |
| Basis | 2.121 | -19.062 | -3.677a | Basis | 1.209 | -11.377 | -2.721 |
| Trading day 9 |  |  |  | Trading day 19 |  |  |  |
| Futures | 1.646 | -6.314 | -1.797 | Futures | 1.802 | -11.630 | -2.305 |
| Spot | 3.373 | -8.718 | -2.996 | Spot | 1.439 | -15.922 | - 3.568a |
| Basis | 1.222 | -20.087 | - 4.808b | Basis | 2.376 | -13.831 | -2.460 |
| Trading day 10 |  |  |  | Trading day 20 |  |  |  |
| Futures | 1.642 | - 14.631 | -3.379 | Futures | 5.323 | - 4.411 | -1.274 |
| Spot | 1.584 | - 11.113 | 2.482 | Spot | 1.530 | -8.342 | -1.821 |
| Basis | 2.024 | -19.730 | 4.017a | Basis | 0.369 | -12.938 | - 2.891 |

Notes: Critical values 1%, 5%

J-statistic 0.117, 0.294

$Z _ { \alpha }$statistic - 27.702, - 20.724

Z statistic - 4.144, - 3.540

<sup>a</sup> For$H _ { 0 } { \mathrm { : } }$I(1); reject null at 5% signi®cance level.

<sup>b</sup> For$H _ { 0 } \ I ( 1 )$reject null at 1% signi®cance level.

The t-statistics of the slope coecient estimators show
clearly that spot price changes and futures price changes are
signi®cantly positively correlated. The coe cient estimates
are similar in magnitudes to those in the CCR. This con-
®rms the CCR ®ndings. The signi®cant positive correlations
between stock index price changes and the corresponding
futures price changes are also reported in other studies such
as Kawaller et al. (1987) and Lim (1991b).

Using the CCR estimates reported in Table 2, I also test if
these estimates are signi®cantly di erent from unity. The
test statistics and p-values are reported in Table 4. The null
hypothesis of unit slope cannot be rejected at the 5% signi®-
cance level for 13 out of the 20 days. If I eliminate the cases
of non-cointegration , as discussed earlier, the null cannot be
rejected in 8 out of 12 days. This turns out to be about 67%
of the cases. This means that both price changes are highly
correlated.

Table 2. Canonical cointegrating regression of spot price on futures price of the Nikkei 225 contract

|  |  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Contract | Constant | Time | Futures | \chi _ { 2 } ^ { 2 } | Contract | Constant | Time | Futures | \chi _ { 2 } ^ { 2 } |
| June 1988 |  |  |  |  | June 1989 |  |  |  |  |
| Trading day 1 Coefficients | 1406.336 | 495.935 | 0.944 | 9.217 | Trading day 11 Coefficients | 26557.046 | -92.075 | 0.172 | 2.471 |
| p-value | (0.452) | (0.026) | (0.021) | (0.010)a | p-value | (0.022) | (0.665) | (0.331) | (0.291) |
| Trading day 2 Coefficients | -711.757 | 157.332 | 1.025 | 2.390 | Trading day 12 Coefficients | 2731.782 | 857.874 | 0.899 | 9.992 |
| p-value | (0.476) | (0.131) | (0.013) | (0.303) | p-value | (0.392) | (0.001) | (0.002) | (0.007)b |
| Trading day 3 Coefficients | 7169.333 | 321.770 | 0.728 | 6.733 | Trading day 13 Coefficients | -14130.316 | 353.290 | 1.419 | 2.839 |
| p-value Trading day 4 | (0.072) | (0.015) | (0.000) | (0.035)a | p-value Trading day 14 | (0.002) | (0.063) | (0.000) | (0.242) |
| Coefficients p-value Trading day 5 | 9106.653 (0.168) | 311.118 (0.067) | 0.658 (0.035) | 5.764 (0.056) | Coefficients p-value Trading day 15 | 1359.120 (0.448) | 274.749 (0.074) | 0.952 (0.002) | 4.397 (0.111) |
| Coefficients p-value | 10936.946 (0.000) | 165.030 (0.021) | 0.592 (0.000) | 3.245 (0.197) | Coefficients p-value | 23446.772 (0.001) | 842.053 (0.004) | 0.295 (0.079) | 10.597 (0.005)b |
| September 1988 Trading day 6 |  |  |  |  | September 1989 Trading day 16 |  |  |  |  |
| Coefficients p-value | 12502.338 (0.031) | 236.758 (0.063) | 0.558 (0.010) | 8.680 | Coefficients p-value | 9978.626 (0.388) | 642.750 (0.051) | 0.711 | 3.955 (0.138) |
| Trading day 7 |  |  |  | (0.013)a | Trading day 17 |  |  | (0.242) |  |
| Coefficients p-value | 3846.225 (0.401) | 289.014 (0.127) | 0.868 (0.060) | 3.074 (0.215) | Coefficients p-value | -1700.521 (0.386) | 130.498 (0.119) | 1.041 | 3.865 (0.145) |
| Trading day 8 |  |  |  |  | Trading day 18 |  |  | (0.000) |  |
| Coefficients | 7455.679 | 95.913 | 0.733 | 3.320 | Coefficients | 696.050 | 261.977 | 0.973 | 34.272 |
| p-value | (0.254) | (0.349) | (0.037) | (0.190) | p-value | (0.394) | (0.000) | (0.000) | (0.000)b |
| Trading day 9 |  |  |  |  | Trading day 19 |  |  |  |  |
| Coefficients | 3916.615 | -1151.798 |  |  |  | 24474.287 |  |  |  |
|  |  |  | 0.860 | 6.703 | Coefficients |  | 107.415 | 0.290 | 2.686 |
| p-value | (0.233) | (0.010) | (0.000) | (0.035)a | p-value | (0.000) | (0.204) | (0.047) | (0.261) |
| Trading day 10 |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  | Trading day 20 |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
| Coefficients |  |  |  |  |  | 24290.606 | -168.540 | 0.289 | 11.425 |
|  |  |  | 0.699 |  |  |  |  |  |  |
|  |  | 130.715 |  | 1.420 | Coefficients |  |  |  |  |
|  | 8154.007 |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  | (0.003)b |
|  |  |  |  |  |  |  | (0.069) |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  | (0.004) |  |
| p-value |  |  |  |  |  | (0.000) |  |  |  |
|  |  | (0.269) | (0.015) | (0.492) |  |  |  |  |  |
|  | (0.173) |  |  |  | p-value |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |

Notes:$H _ { 0 } { \mathrm { : } }$cointegration; test statistic is$H ( 1 , 3 ) = \chi ^ { 2 }$d.f. 2; reject H<sub>0</sub> given one-tailed test if H is too large.

<sup>a</sup> Reject H<sub>0</sub> at 5% signi®cance level.

<sup>b</sup> Reject H<sub>0</sub> at 1% signi®cance level.

This result has certain implications on the basis as de®ned
by the dierence of futures price and the spot price. The
basis is then

$$
( \mathbf { 1 } - \mathsf { \beta } ) \boldsymbol { F } _ { t } - \boldsymbol { \alpha } - \boldsymbol { \gamma } t - \boldsymbol { \varepsilon } _ { t }
$$

If b is unity, the basis is stationary except with a determinis-
tic trend provided that the spotÐfutures prices are cointeg-
rated. This happened in 8 out of 20 days using our sample. If
b is not unity in the cointegrated regression, the basis
possesses a unit root as$\boldsymbol { F } _ { t }$is an I(1) process. The results in
Table 4 show that b is often close, if not equal to, unity.
Thus, any signi®cant appearance of a unit root in the basis is
due more to the fact that the spot and futures prices are not
cointegrated. This suggestion is corroborated by the empiri-
cal evidence presented in Table 1 that the basis is mostly an
I(1) process.

If the regression is not cointegrated, then whether or not
b is unity, the basis possesses a unit root due to$\varepsilon _ { t }$being I(1).
In trading days 1, 3, 6, 18 and 20, in which non-cointegra-
tion is detected as in Table 2, the basis is also shown to be
I(1) as reported in Table 1. And in trading days 5, 6, 11, 19
and 20, in which b is unlikely to be unity, as reported in
Table 4, the bases as reported in Table 1 are also shown to
be I(1). Empirically, these two possibilities of either
non-cointegration or else non-unit b explain most of the
cases of I (1) basis.

Table 3. Estimating optimal futures hedging coe¦cients of the Nikkei 225

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Contract | Constant | β | F-value | Contract | Constant | β | F-value |
| June 1988 |  |  |  | June 1989 |  |  |  |
| Trading day 1 |  |  |  | Trading day 11 |  |  |  |
| Coefficients | 0.935 | 0.910 | 15.482 | Coefficients | -1.788 | 0.244 | 1.073 |
| p-value | (0.296) | (0.000) | (0.000) | p-value | (0.278) | (0.106) | (0.351) |
| Trading day 2 |  |  |  | Trading day 12 |  |  |  |
| Coefficients | -0.897 | 0.898 | 11.196 | Coefficients | - 6.158 | 0.869 | 12.450 |
| p-value | (0.316) | (0.000) | (0.000) | p-value | (0.057) | (0.000) | (0.000) |
| Trading day 3 |  |  |  | Trading day 13 |  |  |  |
| Coefficients | 2.296 | 0.741 | 26.099 | Coefficients | 2.022 | 0.477 | 6.707 |
| p-value | (0.084) | (0.000) | (0.000) | p-value | (0.271) | (0.000) | (0.003) |
| Trading day 4 |  |  |  | Trading day 14 |  |  |  |
| Coefficients | - 0.109 | 0.329 | 2.356 | Coefficients | 4.105 | 0.261 | 2.800 |
| p-value | (0.528) | (0.024) | (0.107) | p-value | (0.087) | (0.066) | (0.071) |
| Trading day 5 |  |  |  | Trading day 15 |  |  |  |
| Coefficients | -0.775 | 0.305 | 16.787 | Coefficients | -0.370 | 0.502 | 8.473 |
| p-value | (0.735) | (0.000) | (0.000) | p-value | (0.438) | (0.000) | (0.001) |
| September 1988 |  |  |  | September 1989 |  |  |  |
| Trading day 6 |  |  |  | Trading day 16 |  |  |  |
| Coefficients | 0.466 | 0.414 | 13.898 | Coefficients | -3.171 | 0.483 | 1.168 |
| p-value | (0.341) | (0.000) | (0.000) | p-value | (0.242) | (0.081) | (0.325) |
| Trading day 7 |  |  |  | Trading day 17 |  |  |  |
| Coefficients | -1.308 | 0.443 | 14.119 | Coefficients | -1.265 | 0.957 | 14.145 |
| p-value | (0.847) | (0.000) | (0.000) | p-value | (0.397) | (0.000) | (0.000) |
| Trading day 8 |  |  |  | Trading day 18 |  |  |  |
| Coefficients | -4.854 | 0.512 | 22.159 | Coefficients | -4.634 | 0.827 | 2.499 |
| p-value | (0.008) | (0.000) | (0.000) | p-value | (0.280) | (0.019) | (0.105) |
| Trading day 9 |  |  |  | Trading day 19 |  |  |  |
| Coefficients | -4.367 | 0.335 | 4.861 | Coefficients | -5.292 | 0.287 | 5.923 |
| p-value | (0.132) | (0.003) | (0.012) | p-value | (0.014) | (0.010) | (0.006) |
| Trading day 10 |  |  |  | Trading day 20 |  |  |  |
| Coefficients | 2.870 | 0.548 | 6.628 | Coefficients | -1.758 | 0.381 | 1.162 |
| p-value | (0.190) | (0.000) | (0.003) | p-value | (0.385) | (0.075) | (0.331) |

When the basis$b _ { t }$follows a unit root process, I can write

$$
b _ { t } = b _ { t - 1 } + \eta _ { t }
$$

where$\eta _ { t }$is a residual error not correlated with$b _ { t ^ { - } 1 }$, but is
not necessarily mean zero or independent over time. This
implies that intraday traders can obtain the best prediction
about future basis movement by taking note of the past
basis movements. Information on the future basis changes
are fully incorporated in the current basis. However, it is
imperative that such traders watch and trade on a continual
basis in order to pro®t from the past basis information. This
is because, if the interval for forecast of future basis is
widened, then since$b _ { t }$is an I(1) process, its variance in-
creases over time. This increased variance introduces unnec-
essary uncertainties and risk for traders. The risk is mini-
mized when the forecast is made on a continual basis. That
this indeed is the case explains the proliferation of individual
trades (also called independents on the SIMEX exchange
¯oor). These trades are typically in small orders and the
traders would buy and sell continually. Of course, if$b _ { t }$is
stationary, then whatever the interval of forecast, the uncer-
tainty remains the same.

## V. CONCLUSION

I have raised an issue regarding the optimal hedging of spot
positions using futures. Employing the Nikkei 225 stocks
and the Nikkei 225 futures, there is evidence that the
spotÐfutures prices are not necessarily cointegrated on some
trading days even though their ®rst dierences are station-
ary. Non-cointegratio n in the price levels implies that the
value of the hedged portfolio, in particular the minimum
variance hedged portfolio, follows an I(1) process, or more
speci®cally, a random walk. Such a price risk has not been
well known in the existing literature on hedging, as far as
I know.

Table 4. Canonical cointegrating regression of spot price on futures
price: a test of unit optimal hedge ratio of the Nikkei 225 contracts

|  |  |  |
| --- | --- | --- |
| Trading day | t-statistic | p-value |
| 1 | -0.124 | (0.451) |
| 2 | 0.057 | (0.477) |
| 3 | -1.470 | (0.074) |
| 4 | - 0.961 | (0.171) |
| 5 | - 6.490 | (0.000)b |
| 6 | -1.892 | (0.032)a |
| 7 | - 0.242 | (0.405) |
| 8 | -0.664 | (0.255) |
| 9 | - 0.707 | (0.242) |
| 10 | -0.974 | (0.168) |
| 11 | - 2.114 | (0.020)a |
| 12 | - 0.329 | (0.372) |
| 13 | 2.936 | (0.003)b |
| 14 | -0.155 | (0.439) |
| 15 | -3.432 | (0.001)b |
| 16 | - 0.288 |  |
| 17 | 0.250 | (0.388) |
|  | -0.364 | (0.402) |
| 18 | - 4.215 | (0.360) |
| 19 20 | -7.234 | (0.000)b (0.000)b |

Note:$H _ { 0 } { \mathrm { : } }$slope coecient = 1.

<sup>a</sup> Reject$H _ { 0 }$at 5% signi®cance level.

<sup>b</sup> Reject$H _ { 0 }$at 1% signi®cance level.

I also provide unit root tests showing evidence that the
basis is mostly an I (1) process. This is consistent with both
cases of spotÐfutures cointegration or non-cointegration ,
provided the slope coecient of the spot price on futures
price is not unity. Even if the slope is unity, non-cointegra-
tion in the spot-futures prices would induce an I (1) basis.
A basis that possesses a random walk, a special case of I(1),
implies that it is most pro®table for intratraders to use basis
knowledge to trade on a continual basis.

This study contributes to the existing literature by char-
acterizing hedged portfolio as well as basis behaviours in the
cointegration framework. Empirical tests on the cointegra-
tion framework are performed and interesting ®nancial
implications are drawn.

## ACKNOWLEDGEMENT

The author acknowledges the help of Sam Ouliaris in pro-
viding the cointegration programming softwares.

## REFERE NCES

Bailey, W. (1989) The market for Japanese stock index futures:
some preliminary evidence, Journal of Futures Markets, 9,
283Ð95.

Baillie, R. T. and Bollerslev, T. (1989) Common stochastic trends
in a system of exchange rates, Journal of Finance, XLIV,
167Ð81.

Brenner, M., Subrahmanyam, M. G. and Uno, J. (1989) The
behavior of prices in the Nikkei spot and futures market,
Journal of Financial Economics, 23, 363Ð83.

Corbae, D. and Ouliaris, S. (1988) Cointegration and tests of
purchasing power parity, Review of Economics and Statistics,
70, 508Ð11.

Corbae, D., Lim, K. G. and Ouliaris, S. (1992) On cointegration
and tests of forward market unbiasedness, Review of Eco-
nomics and Statistics, 74, 728Ð32.

Ederington, L. H. (1979) The hedging performance of the new
futures market, Journal of Finance, 34, 157Ð70.

Engle, R. F. and Granger, C. W. J. (1987) Cointegration and error
correction: representation, estimation and testing, Econo-
metrica, 55, 251Ð76.

Figlewski, S. (1984) Hedging performance and basis risk in stock
index futures, Journal of Finance, 39, 657Ð69.

Figlewski, S. (1985) Hedging with stock index futures: theory and
application in a new market, Journal of Futures Markets, 5,
183Ð99.

Frankcle, C. T. (1980) The hedging performance of the new futures
market: comment, Journal of Finance, 35, 1273Ð79.

Granger, C. W. J. and Newbold, P. (1974) Spurious regressions in
econometrics, Journal of Econometrics, 2, 111Ð20.

Kawaller, I. G., Koch, P. D. and Koch, T. W. (1987) The temporal
price relationship between S&P 500 futures and the S&P 500
index, Journal of Finance, XLII, 1309Ð29.

Lim, K. G. (1992a) Arbitrage and price behavior of the Nikkei
stock index futures, Journal of Futures Markets, 12, 151Ð61.

Lim, K. G. (1992b) Speculative, hedging and arbitrage e ciency of
the Nikkei index futures, in PaciÞc-Basin Capital Markets
Research, Vol. III, eds. S.G. Rhee and R.P. Chang, North-
Holland, Amsterdam, pp. 441Ð61.

Lim, K. G. and Phoon, K. F. (1991) Tests of rational bubbles
using cointegration theory, Applied Financial Economics, 1,
85Ð88.

Park, J. Y. (1988) Canonical cointegrating regressions, CAE Work-
ing Paper 88-29, Cornell University, Ithaca NY.

Park, J. Y. and Choi, B. (1988) A new approach to testing for a unit
root, CAE Working Paper 88-23, Cornell University, Ithaca
NY.

Park, J. Y. and Phillips, P. C. B. (1988) Statistical inferences in
regressions with integrated processes 1, Econometric Theory,
4, 468Ð97.

Phillips, P. C. B (1986) Understanding spurious regressions in
econometrics, Journal of Econometrics, 13, 311Ð40.

Phillips, P. C. B. (1987) Time series regression with a unit root,
Econometrica, 55, 277Ð301.

Stock, J. H. (1987) Asymptotic properties of least squares es-
timators of cointegrating vectors, Econometrica, 55,
1035Ð56.

Stulz, R. M. (1984) Optimal hedging policies, Journal of Financial
and Quantitative Analysis, 19, 127Ð40.

Ziemba, W. T. (1988) Seasonality eects in Japanese futures
markets, in PaciÞc-Basin Capital Markets Research,
ed. S. G. Rhee and R. P. Chang, North-Holland, Amsterdam,
379Ð407.
