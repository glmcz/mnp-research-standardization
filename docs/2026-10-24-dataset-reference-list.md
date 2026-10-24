# Martin's dataset reference list, and what became of each link (2026-10-24)

Martin compiled this list of micro- and nanoplastic water datasets, then fetched what he could into
`~/Downloads/datasets`. `tool/survey/fetch_user.py` copies the data files the survey reads into
`data/raw/datasets_user/` (gitignored) and fetches RIVM's Git LFS files, which a plain clone leaves
as 130-byte pointers.

| Source | Link | Status in the survey |
|---|---|---|
| NOAA NCEI marine microplastics | ncei.noaa.gov/products/microplastics | **In** (pinned hub export, 18 461 records). Martin's fresh FeatureServer pull has 15 808 records; not swapped in, so earlier results stay reproducible. |
| AOMI (Japan MOE) | aomi.env.go.jp | Interactive map, no bulk download. Its basis, Isobe et al. 2021, is **in**. |
| EMODnet floating micro-litter | emodnet.ec.europa.eu | Baltic file **in**. The European v2024 aggregate (found by the scout) is a lead: one row per particle category. |
| LITTERBASE | litterbase.awi.de | View-only by design. |
| Isobe et al. 2021, multilevel | microplastics.springeropen.com | **In** (8 218 samples, via the archive the scout found). |
| Global inland waters, Jin et al. 2025 | nature.com/articles/s43247-025-02320-2 | **Not usable.** Exported with R (`tool/survey/export_jin.R`), the figshare deposit (10.6084/m9.figshare.28784873) holds only fitted random-forest models. Their training tables give per row a transformed abundance and five environmental predictors (human index, AET, cropland, runoff, PET): no coordinates, date, study, unit or size window. The raw table the paper's code loads (`DATA.MPS.Rdata`) is not in the deposit; it would have to be requested from the authors. |
| Global lakes compilations (2) | sciencedirect.com | Paywall, HTTP 403. |
| RIVM MicroplasticsERA_water | github.com/rivm-syso | **In**: 83 Dutch surface-water samples with size windows (`Particle_concentrations_total.rds`, LFS). |
| DURUM urban stormwater | github.com/abdulmobinibnahafiz | **In**: 180 sampling efforts with size windows. The Kaggle mirror is not needed. |
| Meijer river emissions | plastiverse.org | Model output, not measurements; out of scope. |
| Bangshi River | zenodo.org/records/14226568 | One summary sheet of shares by shape and colour, with no concentration per place: not usable. |
| Oregon rivers, Valine et al. | zenodo.org/records/3901297 | **In**: 22 samples. Concentration computed as Nile Red count over volume; no size window in the file. |
| CA drinking water, Moore Institute | github.com/Moore-Institute-4-Plastic-Pollution-Res | **In**: 613 bottled and tap samples, country only. The finest filter per study is the lower limit. |
| CA drinking water, accredited labs | lab.data.ca.gov | Host does not resolve (DNS), for Martin as well. |
| Koelmans et al. 2019 | PMC6449537 | Already used as D3; a compilation of study means. |
| SIPIBEL | PMC8713128 | Data behind Data in Brief / Mendeley; not fetched. |
| SCCWRP WWTP report | sccwrp.org | PDF tables only; not parsed. |
| SF Bay (SFEI) | data.cnra.ca.gov | **In**: 65 manta tows and 22 sediment grabs (blanks left out). Counts are microparticles, mostly not characterised, so the unit says microparticles. Python's client is refused; a curl download worked. |
| ToMEx 2.0 | microplastics.sccwrp.org | Toxicity, not environmental concentrations; out of scope. |
| Directories (Plastiverse, DOER, IWP, data.gov) | various | Indexes for the scout agents, not datasets. |
