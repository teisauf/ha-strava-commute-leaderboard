# Strava Commute Leaderboard for Home Assistant

En Home Assistant custom integration der trækker commute-markerede aktiviteter fra Strava for to (eller flere) atleter, aggregerer YTD-stats og eksponerer head-to-head leaderboard-sensorer — perfekt til husstande der konkurrerer om flest pendlerkilometer.

Data hentes **én gang dagligt kl. 18:00 lokal tid**. Der eksponeres også en `strava_commute_leaderboard.refresh` service til manuel opdatering.

---

## Krav

- Home Assistant 2024.4 eller nyere
- [HACS](https://hacs.xyz/) installeret
- En Strava API-app (se nedenfor)
- `custom:bar-card` og `custom:apexcharts-card` (installeres via HACS → Frontend) hvis du vil bruge det medfølgende dashboard-eksempel

---

## 1. Opret en Strava API-app

1. Log ind på [strava.com/settings/api](https://www.strava.com/settings/api).
2. Udfyld:
   - **Application Name**: `Home Assistant Commute` (eller hvad du vil)
   - **Category**: `Data Importer`
   - **Website**: `http://homeassistant.local` (eller HA's URL)
   - **Authorization Callback Domain**: `my.home-assistant.io` ← **vigtigt**
3. Klik **Create** og noter **Client ID** og **Client Secret**.

Bemærk: Hver atlet skal bruge sin egen Strava API-app med eget **Client ID** og **Client Secret**.

---

## 2. Installér integrationen via HACS

1. I HA: **HACS → Integrations → ⋮ → Custom repositories**
2. Tilføj URL til dette repo, kategori: **Integration**
3. Søg efter **Strava Commute Leaderboard** og installer
4. Genstart Home Assistant

---

## 3. Registrér Strava credentials i HA

1. **Settings → Devices & Services → + Add Integration → Strava Commute Leaderboard**
2. Udfyld atlets **visningsnavn**, **Client ID** og **Client Secret** fra afsnit 1.
3. HA sender dig videre til Strava — log ind med **din egen** konto og autorisér.

### Tilføj partneren

4. Gentag **Add Integration → Strava Commute Leaderboard**.
5. Partneren udfylder eget visningsnavn + eget **Client ID/Client Secret** (fra partnerens egen Strava API-app).
6. Partneren logger ind på Strava (nemt hvis I gør det på partnerens telefon/PC).

---

## 4. Tilpas beregningsparametre (valgfrit)

**Settings → Devices & Services → Strava Commute Leaderboard → Configure**

- **CO₂ per km**: standard `0,192 kg` (EU-gennemsnit personbil)
- **Penge per km**: standard `2,23 DKK` (statens lave takst 2026)
- **Valutasymbol**: standard `DKK`
- **Streak-tolerance**: standard `3` arbejdsdage (streak bryder ikke før 3+ arbejdsdage i træk uden commute — tillader sygdom/hjemmearbejde)

Ændringer gælder pr. atlet.

---

## 5. Dashboard

En færdig Lovelace-view findes i [`dashboard-example.yaml`](dashboard-example.yaml). Kopiér indholdet ind i en ny dashboard-view (Raw configuration editor) og tilpas entity-navnene `teis`/`anna` så de matcher dine visningsnavne.

---

## Sensorer

Pr. atlet (`{name}` = slugificeret visningsnavn, f.eks. `teis`):

| Entity | Beskrivelse |
|---|---|
| `sensor.{name}_distance_ytd` | Samlede commute-km år-til-dato |
| `sensor.{name}_rides_ytd` | Antal commute-ture |
| `sensor.{name}_time_ytd` | Samlet bevægelsestid (timer) |
| `sensor.{name}_elevation_ytd` | Samlet højdemeter |
| `sensor.{name}_avg_speed` | Gns. fart i km/t |
| `sensor.{name}_streak_current` | Nuværende streak (pendledage) |
| `sensor.{name}_streak_longest` | Årets længste streak |
| `sensor.{name}_days_this_month` | Dage med mindst én commute denne måned |
| `sensor.{name}_last_ride` | Tidspunkt for seneste commute |
| `sensor.{name}_co2_saved` | Estimeret CO₂-besparelse (kg) |
| `sensor.{name}_money_saved` | Estimeret penge sparet vs. bil |

Husstand-sammenligning (oprettes når der er ≥ 2 atleter — device: **Commute Leaderboard**):

| Entity | Beskrivelse |
|---|---|
| `sensor.commute_leaderboard_leader` | Navn på atleten der fører i km YTD |
| `sensor.commute_leaderboard_margin_km` | Forskel i km mellem 1. og 2. plads |
| `sensor.commute_leaderboard_margin_percent` | Forskel i procent |
| `sensor.weekly_wins_{name}` | Antal uger hvor atleten har ført i ugens commute-km |

> Tjek de faktiske entity IDs under **Developer Tools → States** efter installation — HA kan tilføje et suffix hvis et ID kolliderer. Du kan altid omdøbe entities.

---

## Services

### `strava_commute_leaderboard.refresh`

Ingen parametre. Trigger en fetch for alle atleter med det samme (i stedet for at vente til næste 18:00).

```yaml
action: strava_commute_leaderboard.refresh
```

---

## Fejlfinding

**Sensorer er `unavailable` efter installation**
Det tager et kort øjeblik før første fetch er færdig. Tjek **Settings → System → Logs** for fejl. Hvis du ser `401 Unauthorized`, har du sandsynligvis givet forkert Client Secret eller har afvist scope `activity:read_all`.

**Commute-ture tæller ikke med**
Verificér at aktiviteten i Strava er markeret som **"Commute"** (boolean-feltet `commute: true`) og har type `Ride`, `EBikeRide` eller `VirtualRide`. Almindelige tags i beskrivelsen er ikke nok.

**Data opdaterer sig ikke**
Integrationen poller kun kl. 18:00. Kald `strava_commute_leaderboard.refresh` via **Developer Tools → Services** for manuel opdatering.

**Rate limit**
Strava's grænser er ~600 requests/15 min og ~30.000/dag. Med kun ét dagligt poll per atlet rammer du dem aldrig.

---

## Arkitektur (kort)

```
custom_components/strava_commute_leaderboard/
├── __init__.py                # daglig trigger kl. 18, refresh-service
├── application_credentials.py # OAuth2-endpoints
├── config_flow.py             # per-atlet flow + options
├── coordinator.py             # fetch + cache + aggregation + streak
├── api.py                     # tynd Strava-klient (pagineret)
├── sensor.py                  # 11 per-atlet + 4 husstand-sensorer
├── const.py
├── strings.json
└── translations/{da,en}.json
```

- Hver atlet = én `ConfigEntry` med sin egen coordinator og OAuth-session
- Aktiviteter caches til `.storage/strava_commute_{athlete_id}` — overlever HA-restart og undgår re-fetch af hele året
- Kun aktiviteter efter sidste fetch hentes (param `after`)
- Streak og alle YTD-tal beregnes rent fra cached data

---

## Licens

MIT
