# GARMIN_INSIGHTS_M0_AUDIT

**Status:** M0 input audit – för godkännande före Insight-implementation  
**Datum:** 2026-09-05  
**Arbetsgren:** `feature/garmin-insights-audit`  
**Baslinje:** `feature/garmin-fitness` efter Fitness-handoff  
**Produktionskod ändrad i M0:** Nej

---

## 1. Sammanfattning

Auditen visar att Garmin Connect-integrationen redan har betydligt mer användbar Insight-input än de tio nya Garmin Fitness-entiteterna antyder.

Det finns redan live/current-state data för:

- Training Readiness
- Morning Training Readiness
- Recovery Time
- Garmin Training Status
- HRV status, veckomedel, senaste natt och Garmin-baseline
- resting HR + 7-dagars medel
- sleep score, sleep need och sömnstadier
- Body Battery
- stress
- VO2max
- Endurance Score / Hill Score
- aktivitetstyp, duration, puls, Training Effect och Garmin Training Load
- de canonical Fitness-serier som redan är låsta: Daily Load, CTL, ATL, TSB, ACWR, Ramp Rate, Strain och Load Focus

Det räcker för en konservativ och förklarbar **Insights V1** utan nya Garmin-endpoints.

Den stora luckan är inte mängden rådata utan **historik, datum/provenance och freshness-semantik**. Nuvarande presentation-sensorer får därför inte bli Insight-motorns primära datakälla.

Viktigaste M0-slutsatsen:

> Insight-regler ska inte läsa Home Assistant-entity states som source of truth. Engine-input ska byggas från daterad, normaliserad Garmin/Fitness-data innan presentation/preserve-value/fallback-lagret.

---

## 2. Arkitekturbaslinje

Fitness-handoff är färdig och ska behandlas som låst.

```text
Garmin API
    ↓
ha-garmin
    ├─ Garmin-normalisering
    ├─ strict history
    └─ Fitness math
         ↓
Home Assistant integration
    ├─ coordinators
    ├─ entities
    ├─ Recorder/statistics
    └─ presentation/provenance
```

Insights ska läggas ovanpå denna separation, inte återinföra matematik eller historiklogik i Lovelace.

### Scope guard

Insights-arbetet får inte ändra:

- TRIMP
- CTL / ATL / TSB
- ACWR
- Ramp Rate
- Strain
- Load Focus
- Fitness entity IDs
- Gear/deviceId-arbetet

---

## 3. Befintlig Insight-input i Home Assistant-integrationen

### 3.1 Training / recovery

Nuvarande `TRAINING_SENSORS` innehåller bland annat:

| Input | Nuvarande källa | Bedömning |
| --- | --- | --- |
| Training Readiness | `trainingReadiness.score` | Stark current-state signal |
| Recovery Time | `trainingReadiness.recoveryTime` | Stark current-state signal |
| Garmin Training Status | `trainingStatus` | Bra kontext, Garmin-proprietär |
| Morning Training Readiness | score + level | Stark morgonsignal |
| Morning sleep score | readiness-attribut | Bra recovery-komponent |
| Morning recovery score | readiness-attribut | Bra recovery-komponent |
| Morning HRV status | readiness-attribut | Bra recovery-komponent |
| Morning acute load | readiness-attribut | Bra kontext, inte canonical Fitness load |
| HRV status | Garmin status | Stark Garmin-kontext |
| HRV weekly average | ms | Bra kort baseline/trend |
| HRV last-night average | ms | Stark nightly signal |
| HRV 5-min high | ms | Sekundär signal |
| HRV baseline | Garmin baseline + attrs | Mycket värdefull för V1 |
| VO2max | training-status-derived | Fitness/trend-signal |
| Endurance Score | Garmin-native | Fitness-signal |
| Hill Score | Garmin-native | Sportspecifik sekundär signal |

### 3.2 Core / recovery physiology

Nuvarande CORE-sensorer innehåller:

| Input | Nuvarande data |
| --- | --- |
| Resting HR | dagens Garmin-värde |
| 7-day avg resting HR | Garmin 7-dagars medel |
| Average/max stress | Garmin stress |
| Stress duration/percentages | flera nivåer |
| Sleep score | Garmin sleep score |
| Sleep need | minuter |
| Total sleep | minuter |
| Deep/light/REM/awake | minuter |
| Nap time | minuter |
| Body Battery current/high/low | procent |
| Body Battery charged/drained | procent |
| SpO2 | avg/low/latest |
| Respiration | high/low/latest |

För Insight V1 är resting HR, sleep score/need, Body Battery och stress mest relevanta. SpO2/respiration bör inte användas i träningsrekommendationer utan separat, tydligt definierad regel och försiktig framing.

### 3.3 Activity context

`ha-garmin` behåller redan följande i aktivitetspayload/normalized Fitness ActivityMetrics:

- activity ID
- date/start time
- activity type
- duration
- distance
- avg/max HR
- calories
- aerobic Training Effect
- anaerobic Training Effect
- Garmin activity training load
- VO2max per aktivitet när tillgängligt
- avg/normalized power

Detta räcker för framtida V3-kontext som exempelvis:

- antal träningsdagar
- flera hårda dagar i rad
- senaste kvalitativa pass
- aktivitetstyp som förklaring till belastningsförändring
- Training Effect-baserad kontext

### 3.4 Canonical Training V4

Redan tillgängligt och låst:

- Daily Load
- CTL
- ATL
- TSB
- ACWR 7/28
- Ramp Rate 7d
- Strain
- Low aerobic / High aerobic / Anaerobic Load Focus

Dessa är den primära inputen för belastningsrelaterade Insight-regler.

---

## 4. Den viktigaste datakvalitetsrisken: fallback och preserve-value

Nuvarande vanliga Garmin-sensorer är byggda för bra presentation i Home Assistant, inte för regelmotorer.

Två beteenden är särskilt viktiga:

### 4.1 Garmin fetch-fallback

`fetch_core_data()` och `fetch_training_data()` kan falla tillbaka till gårdagens data när dagens Garmin-data ännu inte finns.

Exempel:

- Training Status kan hämtas från gårdagen om dagens payload saknar användbar VO2max/status.
- HRV faller tillbaka till gårdagen om dagens `hrvSummary` saknas.
- Endurance/Hill Score kan falla tillbaka till gårdagen.
- Core summary kan falla tillbaka till gårdagen om dagens daily summary ännu inte är redo.

Det är bra för UI men innebär att ett state som visas "idag" inte nödvändigtvis är en mätning från idag.

### 4.2 `preserve_value`

Flera recovery-/fitness-sensorer använder `preserve_value=True`.

När Garmin returnerar `None` kan Home Assistant-entiteten därför fortsätta visa föregående kända värde.

Det gäller exempelvis delar av:

- sömn
- stress
- recovery time
- HRV
- VO2max
- lactate threshold

### 4.3 Konsekvens för Insights

En Insight-motor får inte göra:

```text
read sensor state
→ anta att värdet tillhör idag
→ trigga regel
```

Den måste i stället arbeta med:

```text
value
measurement_date
source
freshness/data_age
complete
```

Annars riskerar vi falska rekommendationer baserade på ett gammalt men presentation-preserverat värde.

---

## 5. Historical capability – vad finns redan

`GarminHistoryClient` är redan byggd med strict-history-semantik och undviker UI-fallback.

Den har idag bland annat:

- `get_daily_summary(date)` – exakt datum, ingen fallback
- `get_resting_heart_rate_range(start, end)` – strict range
- `get_activities_by_date(start, end)`
- `fetch_activity_metrics(start, end)`
- `fetch_trimp_training_context(start, end)`

Det är en bra arkitekturell grund.

### Saknas för Insights

Det finns ännu ingen motsvarande strict date-range facade för hela recovery-paketet, exempelvis:

```text
sleep
HRV
training readiness
recovery time
body battery
stress
VO2max/training status measurement date
```

Det är den stora M1-dataluckan.

---

## 6. Föreslagen canonical input-modell

### 6.1 `DailyRecoveryMetrics`

M1 bör definiera en daterad, normaliserad modell ungefär så här:

```yaml
date: 2026-09-05

resting_hr: 48
resting_hr_baseline: 50

hrv_last_night_avg: 42
hrv_weekly_avg: 45
hrv_status: balanced
hrv_baseline_low: 39
hrv_baseline_high: 52

sleep_score: 82
sleep_minutes: 438
sleep_need_minutes: 450

average_stress: 24
body_battery_high: 78
body_battery_low: 22

training_readiness: 71
morning_training_readiness: 76
recovery_minutes: 480

vo2max: 44.0
endurance_score: 5100

provenance:
  hrv_measurement_date: 2026-09-05
  sleep_measurement_date: 2026-09-05
  readiness_measurement_date: 2026-09-05

complete:
  recovery_core: true
  sleep: true
  hrv: true
```

Missing physiological värden ska vara `None`, aldrig fabricerade nollor.

### 6.2 `InsightSnapshot`

Rules bör få ett samlat snapshot, inte HA entity IDs:

```yaml
as_of: 2026-09-05T08:00:00+02:00

recovery: <DailyRecoveryMetrics>
training:
  daily_load: 0
  ctl: 10.3
  atl: 1.0
  tsb: 9.4
  acwr: 0.14
  ramp_rate: -3.7
  strain: 0.0

load_focus:
  low_aerobic: 0.0
  high_aerobic: 0.0
  anaerobic: 0.0

recent_activities: [...]

data_quality:
  complete: true
  stale_fields: []
  missing_fields: []
```

---

## 7. Vad Insights V1 kan göra redan nu

Utan nya Garmin-endpoints kan V1 byggas konservativt runt befintliga current-state-signaler och canonical Fitness-data.

### 7.1 Training load

Möjliga regler:

- ACWR unusually high/low
- tydlig positiv/negativ Ramp Rate
- hög Strain idag
- flera hårda dagar i rad när activity history används
- mycket låg akut load relativt CTL
- Load Focus-obalans

### 7.2 Recovery

Möjliga regler när input är färsk och komplett:

- låg Training Readiness + lång Recovery Time
- låg readiness + negativ TSB / hög ATL
- HRV-status utanför Garmin-baseline + resting HR över 7d-baseline
- svag sömn + låg readiness
- låg Body Battery + hög stress som förstärkande kontext

### 7.3 Positive signal

Exempel:

- hög readiness
- acceptabel TSB
- sömn nära behov
- HRV inom Garmin-baseline
- ingen load-spike

Det kan ge en försiktig "favourable quality-session signal" utan att försöka ge medicinsk rådgivning.

### 7.4 Data quality

V1 bör ha explicita insights för:

- insufficient data
- stale recovery data
- saknad HRV-baseline
- ofullständig Training Effect/load-focus coverage

---

## 8. Vad som INTE är moget ännu

Följande bör vänta tills strict recovery history finns:

- egen 28/90-dagars HRV-trend
- egen resting-HR trend utöver Garmin 7d
- sleep baseline/trend
- Body Battery-trend
- stress trend
- robust fitness-trend med VO2max measurement timestamps
- consistency-insights över längre period
- multi-signal backtesting av Insight-regler

Detta är alltså en historikfråga, inte en endpoint-brist i första hand.

---

## 9. Rekommenderad ansvarsfördelning

### `ha-garmin`

Bör äga:

- strict date-specific/range Garmin access
- normaliserade `DailyRecoveryMetrics`
- provenance / measurement date
- freshness-friendly data shape
- pure deterministic insight models/rules
- trend/baseline helpers som inte är Home Assistant-specifika

### Home Assistant integration

Bör äga:

- Insight coordinator/orchestration
- kombinera recovery + Training V4 + activity context
- entity lifecycle
- Recorder/LTS backfill för utvalda recovery metrics
- current insight entities/attributes
- notifications om vi senare vill ha det

### Lovelace

Bör endast:

- presentera insights
- visa severity/category/reason/metrics
- filtrera/sortera

Ingen Insight-regel eller threshold-logik ska ligga i Lovelace.

---

## 10. Föreslagen Insight-modell

Roadmapens modell är fortsatt bra:

```yaml
id: recovery_hrv_rhr
category: recovery
severity: info

title: Återhämtningen ser pressad ut
message: HRV ligger under din baseline samtidigt som vilopulsen ligger över sin baseline.

reason:
  - hrv_below_baseline
  - resting_hr_above_baseline

metrics:
  hrv_last_night_avg: 36
  hrv_baseline_low: 40
  resting_hr: 55
  resting_hr_baseline: 50

created_at: ...
expires_at: ...
algorithm_version: 1
```

Varje rule måste kunna förklara exakt vilka metrics som utlöste den.

---

## 11. M1 – rekommenderad datagrund före full Insight-engine

### Steg 1 – lås input-kontrakt

Definiera:

- `DailyRecoveryMetrics`
- `InsightSnapshot`
- provenance/freshness-semantik

### Steg 2 – bygg strict recovery history i `ha-garmin`

Minimikandidat:

```text
fetch_recovery_day(date)
fetch_recovery_history(start, end)
```

Internt ska befintliga Garmin-endpoints återanvändas; inga duplicerade auth/session-lager.

### Steg 3 – historisk backfill

Första mål: 28 dagar recovery-data.  
Andra mål: 90 dagar för Trends/Insights.

Backfill måste vara resumable och API-snålt.

### Steg 4 – provenance/freshness

Varje recovery metric ska kunna skilja:

- requested date
- actual measurement date
- stale/fresh
- missing

### Steg 5 – pure rules

Första regelsatsen:

1. training load spike
2. recovery caution
3. favourable quality-session signal
4. low-load/detraining context
5. load-focus imbalance
6. insufficient/stale data

### Steg 6 – tester

Varje rule kräver:

- trigger
- non-trigger
- threshold boundary
- missing data
- stale data
- mixed fresh/stale data

### Steg 7 – HA entity layer

Först när rules och inputs är stabila.

### Steg 8 – UI sist

Insights dashboard/kort ska byggas på färdiga Insight-objekt.

---

## 12. M0-beslut som rekommenderas för låsning

1. Befintlig Garmin-data räcker för en användbar Insight V1.
2. HA entity states får inte vara canonical engine-input.
3. Daterad provenance/freshness är obligatorisk.
4. Preserve-value/fallback är presentationsegenskaper och får inte smyga in i rules.
5. `GarminHistoryClient` är rätt plats att utöka strict recovery history.
6. Training V4-värden återanvänds oförändrade.
7. Recovery-history byggs som ett separat inputlager, inte som nya Fitness-formler.
8. Insight rules ska vara deterministiska, testbara och förklarbara.
9. Missing data ger insufficient-data, inte gissningar.
10. Ingen UI-logik eller AI behövs för V1.
11. Gear är separat scope och påverkar inte recovery/training-bedömningen.
12. Ingen produktionskod skrivs före godkänt M0/M1-inputkontrakt.

---

## 13. Audit verdict

**GO för Insight-datagrund.**

Det saknas inte "mer Garmin-data" för att börja. Det som behöver byggas först är en strict, daterad recovery-history/inputmodell så att reglerna vet om ett värde verkligen tillhör den dag de analyserar.

När det finns på plats kan Insights V1 byggas ovanpå samma arkitektur som Training V4 utan att röra de låsta Fitness-formlerna.
