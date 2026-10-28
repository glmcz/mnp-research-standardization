# Martin's dataset reference list, and what became of each link (2026-10-24)

Martin compiled this list of micro- and nanoplastic water datasets, then fetched what he could into
`~/Downloads/datasets`. `tool/survey/fetch_user.py` copies the data files the survey reads into
`data/raw/datasets_user/` (gitignored) and fetches RIVM's Git LFS files, which a plain clone leaves
as 130-byte pointers.

| Source | Link | Status in the survey |
|---|---|---|
| NOAA NCEI marine microplastics | ncei.noaa.gov/products/microplastics | **In** (pinned hub export, 18 461 records). Martin's fresh FeatureServer pull has 15 808 records; not swapped in, so earlier results stay reproducible. |
| AOMI (Japan MOE) | aomi.env.go.jp | **In** since 2026-10-26: Martin pulled the open-data layer from the portal's ArcGIS service (18 860 records, particles/m³ under 5 mm, mesh stated). It holds 93 % of Isobe et al. 2021's samples, which it replaced, and about three in four of NOAA's ocean-water records. |
| EMODnet floating micro-litter | emodnet.ec.europa.eu | Baltic density file **in**. The pan-European 2021 aggregate (Martin, 2026-10-26) counts per particle category and gives a filtered volume for 121 Baltic samples only; the rest give a tow length, so a value per m³ would need an assumed net depth: not read. |
| LITTERBASE | litterbase.awi.de | View-only by design. |
| Isobe et al. 2021, multilevel | microplastics.springeropen.com | Replaced by AOMI on 2026-10-26, which holds 93 % of its samples. |
| Global inland waters, Jin et al. 2025 | nature.com/articles/s43247-025-02320-2 | **Not usable.** Exported with R (`tool/survey/export_jin.R`), the figshare deposit (10.6084/m9.figshare.28784873) holds only fitted random-forest models. Their training tables give per row a transformed abundance and five environmental predictors (human index, AET, cropland, runoff, PET): no coordinates, date, study, unit or size window. The raw table the paper's code loads (`DATA.MPS.Rdata`) is not in the deposit; it would have to be requested from the authors. |
| Global lakes compilations (2) | sciencedirect.com | Paywall, HTTP 403. |
| RIVM MicroplasticsERA_water | github.com/rivm-syso | **In**: 83 Dutch surface-water samples with size windows (`Particle_concentrations_total.rds`, LFS). |
| DURUM urban stormwater | github.com/abdulmobinibnahafiz | **In**: 180 sampling efforts with size windows. The Kaggle mirror is not needed. |
| Meijer river emissions | plastiverse.org | Model output, not measurements; out of scope. |
| Bangshi River | zenodo.org/records/14226568 | One summary sheet of shares by shape and colour, with no concentration per place: not usable. |
| Oregon rivers, Valine et al. | zenodo.org/records/3901297 | Out since 2026-10-26: local, and no record shares a place with another study. |
| CA drinking water, Moore Institute | github.com/Moore-Institute-4-Plastic-Pollution-Res | Out since 2026-10-26: a country, no place, so nothing to compare at the same place. |
| CA drinking water, accredited labs | lab.data.ca.gov | Host does not resolve (DNS), for Martin as well. |
| Koelmans et al. 2019 | PMC6449537 | Already used as D3; a compilation of study means. |
| SIPIBEL | PMC8713128 | Data behind Data in Brief / Mendeley; not fetched. |
| SCCWRP WWTP report | sccwrp.org | PDF tables only; not parsed. |
| SF Bay (SFEI) | data.cnra.ca.gov | Out since 2026-10-28. Its 65 manta tows and 22 sediment grabs count microparticles, mostly never characterised, so they share a place with other studies only in a unit no other study counts in. AOMI holds the same tows (doi 10.1021/acsestwater.0c00292) as plastic pieces per m³. |
| GeoPlasticoBR (Brazil) | Martin, 2026-10-27 | **In** since 2026-10-28: 692 water, sediment and soil rows of 1 183; bivalves, corals and echinoderms are body burdens and stay out. No sampling date (the year is the paper's) and no size window, so it joins only the any-year comparison. Its DOI column was filled down: inside one study the DOI counts up into other papers' (Water Research 119707 is the Amazon study, 119708 on steel corrosion; PubMed), so a study keeps its first DOI and 385 rows are flagged; 26 rows are entered twice. One paper, doi 10.1016/j.marpolbul.2019.110705, is also in NOAA or AOMI. Submitters' names and institutions are in the file and are not read. |
| ToMEx 2.0 | microplastics.sccwrp.org | Toxicity, not environmental concentrations; out of scope. |
| Directories (Plastiverse, DOER, IWP, data.gov) | various | Indexes for the scout agents, not datasets. |
