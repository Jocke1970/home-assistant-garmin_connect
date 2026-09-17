# Garmin Fitness – JS-dashboard (frontend dev)

Status: frontend testad parallellt i en riktig Home Assistant-installation den 17 september 2026. Kod läggs endast på `dev`; det här är ingen HACS-release och varken `beta` eller `main` ska påverkas. Backend `3.0.35-beta.1` är separat.

## Arkitektur

- `www/garmin_fitness_card/garmin-fitness-dashboard-card.js`: sammanhållen presentation av insikter, datakvalitet, senaste aktivitet, budget och passutvärdering. Version `0.1.1-dev.2`.
- `www/garmin_fitness_card/garmin-fitness-card.js`: separat, beständigt monterat grafkort för Recorder/LTS och 7/28/42/90 dagar samt tre expandrar. Version `0.1.6-dev.2`.
- Beräkningar sker endast i backend. Dashboarden läser Home Assistant-entiteter, inte Garmins API direkt.
- Grafkortet monteras en gång; HA-state-uppdateringar får inte återskapa det eller återställa period/expander-val.

**Repo-katalogen `www/` är en källkodskopia, inte automatiskt HA:s `/config/www/` och distribueras inte automatiskt till Lovelace av HACS.** Installation är manuell tills en separat distributionslösning är införd.

## Installera i HA för parallelltest

1. Behåll din befintliga fungerande Garmin-vy och eventuell återställningsmöjlighet. Ersätt bara de två JS-filerna i HA:s riktiga `/config/www/garmin_fitness_card/` (eller `/homeassistant/www/garmin_fitness_card/`) när du uttryckligen väljer att prova frontend-versionerna. Behåll befintlig bannerfil i samma katalog; den ingår inte i det här kodpaketet.
2. Under Inställningar → Dashboards → Resurser, använd exakt en JavaScript-modulresurs per fil (redigera redan befintliga resurser, skapa inte dubbletter):

   ```text
   /local/garmin_fitness_card/garmin-fitness-card.js?v=0.1.6-dev.2
   /local/garmin_fitness_card/garmin-fitness-dashboard-card.js?v=0.1.1-dev.2
   ```

3. Ladda om HA-vyn hårt med `Ctrl+Shift+R` och skapa ett separat kort från `examples/garmin_fitness_dashboard_dev.yaml`. Behåll den äldre YAML-stacken tills du har verifierat allt.
4. Kontrollera grafens fyra perioder, alla tre expandrar, passväljaren, datakvalitetsmeddelanden, budgetförklaringen och versionstexternas kontrast.

## Bekräftade observationer i HA

- Faktisk TRIMP 63,4, budgeträknad TRIMP 0,0 och lågintensivt undantagen TRIMP 63,4 visades samtidigt. Det visar den observerade uppdelningen, inte att historiken har skrivits om.
- Faktisk ACWR 2,48 och planeringens ACWR 1,81 har olika underlag: 63,4 TRIMP undantas i planeringen. Presenteras som två separata värden, inte som automatiskt synkfel. Om ett sådant underlag saknas ska vi inte gissa orsaken.
- Budget 0 TRIMP beror här på ACWR-gränsen; texten ska inte säga att budgeten är förbrukad.
- Versionsfötter har läsbar HA-temafärg och 12 px text.
- Test i HA: grafen renderar, perioderna 7/28/42/90 och expandrarna fungerar; insikter, budget och passutvärdering visas.

## Begränsningar och fortsättning

- Frontend- och backend-data kan uppdateras vid olika tidpunkter. Endast visad, verifierad underlagsskillnad förklaras som förväntad; oklara differenser kräver vidare undersökning.
- Ingen ändring av beräkningsmodellen, `ha-garmin`, integrationens manifest eller publicerad beta via denna frontend-commit.
- Gör separat kodgranskning och test av frontend-distribution och versionshantering innan `dev → beta`.

## Lokal kontroll

Från repots rot, med Node.js installerat:

```bash
node --check www/garmin_fitness_card/garmin-fitness-card.js
node --check www/garmin_fitness_card/garmin-fitness-dashboard-card.js
node www/garmin_fitness_card/tests/dashboard.test.cjs
```

Smoke-testerna granskar budgettext, ACWR-förklaring, HTML-escaping, insikter, aktivitet och beständig grafinstans. De ersätter inte fullständiga webbläsar- eller integrationstester.
