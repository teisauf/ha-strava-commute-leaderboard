# Strava Commute Leaderboard

Home Assistant custom integration til at sammenligne pendlerkilometer mellem to Strava-brugere (f.eks. en husstand).

Henter automatisk dagligt kl. 18:00 alle commute-markerede aktiviteter fra Strava og eksponerer YTD-stats per atlet samt head-to-head sammenligningssensorer.

## Hovedfunktioner

- Leaderboard: hvem fører i commute-km år-til-dato
- Per-atlet stats: km, antal ture, tid, højdemeter, gennemsnitsfart
- Streak & pendledage denne måned
- CO₂ & penge sparet vs. bil (konfigurerbar sats)
- Ugentlige head-to-head vindere
- Daglig fetch kl. 18 + manuel `refresh` service
