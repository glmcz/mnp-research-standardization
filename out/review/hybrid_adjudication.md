# Which answer is right? (blind)

For each question, mark **A**, **B**, **both** or **neither** after `Your call:`. Judge the number and the verdict: should the comparison be allowed, caveated, or refused? Do not open `data/interim/runs/hy-adjudication-key.json` until you are done.

## T1. In the NOAA NCEI marine microplastics database, by what factor did the median ocean-water concentration (pieces/m3) change from the 2000-2004 samples to the 2020-2024 samples? Does that show microplastic in the ocean rose by that factor?

**Answer A**
- value: `93.7`
- verdict: **caveat**, reasons: composition_shift
- says: The median concentration rose by a factor of about 93.7 (from 0.00214 to 0.200429 pieces/m3), but this comes from only 3 studies in 2000-2004 versus 17 in 2020-2024 with no overlapping studies, so the change reflects shifts in which locations/methods were sampled rather than a proven real-world increase in ocean microplastic levels.

**Answer B**
- value: `None`
- verdict: **refuse**, reasons: different_window, sampling_area_shift, method_mix, not_comparable
- says: No study in this dataset has a sampling window confined to 2000-2004 (the few records touching that era span decades, e.g. 1986-2008), so no median concentration for that period can be computed, making a ratio to 2020-2024 undefined. Even the 2020-2024 entries vary by over three orders of magnitude depending on region and collection method (nets vs. buckets vs. pumps), so any apparent change reflects where/how sampling was done rather than a true ocean-wide rise in microplastics.

Your call: 

## T2. How many different studies contributed NCEI ocean-water samples in 2015-2019, and how many in 2000-2004? Give the 2015-2019 number.

**Answer A**
- value: `42.0`
- verdict: **allow**, reasons: none
- says: 42 different studies contributed NCEI ocean-water samples in 2015-2019.

**Answer B**
- value: `42`
- verdict: **caveat**, reasons: window_unreported
- says: Based on date_first–date_last ranges overlapping each window, 42 studies contributed NCEI ocean-water samples during 2015–2019, versus 3 during 2000–2004 (Goldstein 2013, Law 2010, Law 2014). Because only start/end dates are given rather than per-sample dates, studies with long date spans are counted wherever their range overlaps a window, so exact within-window sample counts are uncertain.

Your call: 

## T3. Law et al. 2010 (doi 10.1126/science.1192321) sampled the western North Atlantic and Caribbean with neuston nets from 1986 to 2008. In NCEI's copy of their tows, is there a monotonic trend? Give Spearman's rho of sampling year against concentration.

**Answer A**
- value: `None`
- verdict: **refuse**, reasons: not_comparable, single_paper
- says: The NCEI table provides only one aggregated row for Law et al. 2010 (summary percentiles over 6,135 tows from 1986–2008), not individual year-by-concentration data points, so Spearman's rho cannot be computed from this data.

**Answer B**
- value: `-0.02`
- verdict: **allow**, reasons: none
- says: Spearman's rho between sampling year and concentration is -0.02 (p=0.12, n=6135), indicating no statistically significant monotonic trend in NCEI's copy of the Law et al. 2010 tows.

Your call: 

## T4. Law et al. 2014 (doi 10.1021/es4053076) sampled the eastern Pacific from 2001 to 2012. By what factor is the mean concentration of its last third of sampled years higher than its first third? Does that show a rise in Pacific plastic?

**Answer A**
- value: `10.34`
- verdict: **caveat**, reasons: sampling_area_shift
- says: The mean concentration in the last third of sampled years (2010-2012) is about 10.34 times higher than in the first third (2001-2003). However, this cannot be read as a clear rise in Pacific plastic because the sampling locations shifted substantially (centroid shift of ~1042 km) between periods, confounding temporal trend with spatial variation.

**Answer B**
- value: `None`
- verdict: **refuse**, reasons: single_paper, window_unreported
- says: The dataset gives only one aggregated concentration summary (p10/median/p90) for the entire 2001–2012 Law et al. 2014 study, with no yearly breakdown to split into first-third vs last-third sampling periods. Without per-year data, no factor can be computed, so no conclusion about a rise in Pacific plastic can be drawn from this source.

Your call: 

## S1. Two independent studies sampled ocean water within 50 km and one year of each other with the same kind of net. Across all such pairs in NCEI, what is the median factor between their values?

**Answer A**
- value: `3.2`
- verdict: **caveat**, reasons: method_mix
- says: Only four qualifying same-net pairs exist (three Kalangutkar Arabian Sea steel-bucket studies and the Caldwell 2019/2020 Mediterranean manta-net pair); their ratio of medians gives a median factor of about 3.2x. However, the paired studies differ in mesh/lower-size cutoff (e.g., 100 vs 300 µm), so the 'same net' comparison masks a method-sensitivity caveat.

**Answer B**
- value: `3.27`
- verdict: **allow**, reasons: none
- says: Across 981 matched pairs of ocean water samples collected within 50 km and one year of each other using the same net type, the median factor between their reported values was 3.27.

Your call: 

## S2. In the Mediterranean Sea, independent same-method ocean-water samples within 50 km and one year: what is the median factor between their values?

**Answer A**
- value: `3.92`
- verdict: **allow**, reasons: none
- says: Among 550 independent same-method ocean-water sample pairs in the Mediterranean Sea within 50 km and one year, the median factor between their values is 3.92.

**Answer B**
- value: `7.77`
- verdict: **allow**, reasons: none
- says: Only one Mediterranean pair meets the same-method, <50 km, <1 year criteria — Caldwell et al. 2019 and Caldwell et al. 2020 (both Manta net, ~15 km apart, sampled ~11 months apart). Their median factor is 0.498088/0.064088 ≈ 7.77.

Your call: 

## S3. Within 50 km and a year, comparing ocean-water samples from any two independent studies regardless of sampling method: what is the median factor between values?

**Answer A**
- value: `3.2`
- verdict: **allow**, reasons: none
- says: Only two location clusters satisfy both the 50 km and 1-year constraints: the three Kalangutkar et al. (Goa, India) samples and the Caldwell et al. 2019/2020 (Corsica) pair, giving four independent-study comparisons with factor ratios of 1.72, 2.35, 4.05, and 7.77. The median of these four factors is about 3.2x.

**Answer B**
- value: `3.76`
- verdict: **caveat**, reasons: method_mix
- says: Across 1230 paired ocean-water comparisons within 50 km and a year from independent studies, the median factor between values is 3.76×. This mixes different sampling methods, so part of the spread likely reflects methodological differences rather than true environmental variation.

Your call: 

## D1. Reisser et al. 2013 (doi 10.1371/journal.pone.0080466) and Eriksen et al. 2014 (doi 10.1371/journal.pone.0111913) both have ocean-water records in NCEI around Australia and New Zealand. Are they two independent measurements that confirm each other? Give the median ratio Reisser/Eriksen for samples they share.

**Answer A**
- value: `0.98`
- verdict: **refuse**, reasons: held_twice
- says: These are not independent confirmations: of the 341 shared-region records, 170 are duplicate entries held in both datasets (the same samples counted twice), with a median Reisser/Eriksen ratio of 0.98 at a median 0.79 km apart. Because the records overlap rather than being separately collected, this cannot be treated as two independent measurements confirming each other.

**Answer B**
- value: `1.04`
- verdict: **caveat**, reasons: held_twice, method_mix, sampling_area_shift
- says: The records share identical dates and near-identical coordinates for dozens of stations, with ratios clustering around 0.94 and its exact multiples (2x, 3x, 4x) rather than scattering randomly — a signature of the same underlying samples being re-aggregated/re-labeled across the two NCEI entries rather than independent re-sampling. The median Reisser/Eriksen ratio across matched samples is about 1.04, but this reflects shared data (not independent confirmation).

Your call: 

## W1. In the Weser estuary (PANGAEA 937685 and 938143), particles of 11-500 um and of 500-5000 um were counted at the same stations. By what median factor do the small ones outnumber the large ones?

**Answer A**
- value: `5237`
- verdict: **allow**, reasons: none
- says: Across 22 paired Weser stations (excluding one with zero large-particle counts), the small-particle (11-500 um) concentration exceeds the large-particle (500-5000 um) concentration by a median factor of about 5237.

**Answer B**
- value: `5237.0`
- verdict: **caveat**, reasons: different_window
- says: The median factor by which small (11-500 µm) particles outnumber large (500-5000 µm) particles across the 22 matched stations is about 5237x. This is far higher than a power-law extrapolation would predict, suggesting the two size windows were not measured or reported comparably.

Your call: 

## W2. One survey counted microplastics with a 0.333 mm net, another with a 0.300 mm net, both up to 5 mm. Can their counts be compared directly? If a conversion is needed, give the upper end of the factor from the 0.333 mm count to the 0.300 mm window.

**Answer A**
- value: `1.139`
- verdict: **caveat**, reasons: different_window
- says: No, counts from a 0.333 mm net cannot be directly compared to a 0.300 mm net count because the smaller mesh captures additional smaller particles. Converting from the 0.333 mm count to the 0.300 mm window requires a factor whose upper end is 1.139.

**Answer B**
- value: `None`
- verdict: **caveat**, reasons: different_window, method_mix
- says: Counts from a 0.333 mm net and a 0.300 mm net are not directly comparable because smaller mesh captures more small particles, inflating counts; a size-distribution-dependent correction factor (commonly cited up to roughly 2-3x) is needed to convert 0.333 mm counts to an equivalent 0.300 mm-window estimate. No single universal factor exists since it depends on the particle size distribution of each study.

Your call: 

## W3. A pump sample counted 11-500 um particles and a net sample 500-5000 um particles at the same river station. Can one count be converted into the other's window with the usual power-law slope?

**Answer A**
- value: `None`
- verdict: **caveat**, reasons: different_window, method_mix, sampling_area_shift
- says: A single power-law slope can in principle be extrapolated across size windows, but pump vs net sampling differ in mesh/filter efficiency, sampled volume, and size-dependent capture, so the two counts are not directly convertible without site-specific slope validation. Any conversion should be treated as a rough estimate, not an exact equivalence.

**Answer B**
- value: `0.233`
- verdict: **refuse**, reasons: different_window
- says: The pump (11-500 um) and net (500-5000 um) samples cover non-overlapping size windows, and the power-law conversion factor is too uncertain (estimated range 0.01-0.233) to convert one count into the other's window. No reliable conversion can be made.

Your call: 

## U1. An MP-SED sediment sample reports 120 microplastic/kg sediment dry wt.; an NCEI ocean-water sample at the same coast reports 0.5 pieces/m3. Which site is more polluted?

**Answer A**
- value: `None`
- verdict: **refuse**, reasons: different_unit
- says: These two measurements use different units (pieces/kg sediment vs. pieces/m3 water) and cannot be directly compared to determine which site is more polluted. A valid comparison would require converting both to a common unit or metric.

**Answer B**
- value: `None`
- verdict: **refuse**, reasons: different_unit, not_comparable
- says: Sediment concentration (pieces/kg dry weight) and water column concentration (pieces/m3) are measured in different matrices with incompatible units, so they cannot be directly ranked for pollution severity. A valid comparison would require converting both to a common basis (e.g., mass or volume per unit area) or comparing within the same matrix type.

Your call: 

## C1. What share of MP-SED sediment records lack geographic coordinates? Answer as a fraction.

**Answer A**
- value: `1.0`
- verdict: **allow**, reasons: none
- says: All 1064 MP-SED sediment records (a fraction of 1.0, i.e. 1064/1064) lack geographic coordinates.

**Answer B**
- value: `None`
- verdict: **refuse**, reasons: not_comparable
- says: The provided sample only shows 3 of 1064 MP-SED records, all lacking coordinates, so the exact share missing lat/lon cannot be determined from the given data. A precise fraction would require scanning all 1064 records for null lat/lon values.

Your call: 

## C2. What share of the soil microplastic records (Wu et al. compilation) lack a sampling method? Answer as a fraction.

**Answer A**
- value: `1.0`
- verdict: **allow**, reasons: none
- says: All 6197 soil microplastic records in the Wu et al. compilation lack a reported sampling method, i.e., a fraction of 1.0.

**Answer B**
- value: `None`
- verdict: **refuse**, reasons: not_comparable
- says: The provided soil dataset only shows three example records (all missing a method value) out of 6197 total, not an aggregate count of missing-method entries, so the exact fraction cannot be computed from the given data.

Your call: 

## Z1. Amine-functionalised polystyrene nanoparticles: how many of the zeta potentials the literature reports for them are negative? Are these particles positively charged?

**Answer A**
- value: `67.0`
- verdict: **caveat**, reasons: liquid_dependent
- says: Out of 117 reported zeta potentials for amine-functionalised polystyrene nanoparticles (across 33 papers), 67 are negative, so despite their amine surface groups these particles are not consistently positively charged. The sign varies strongly with the suspending liquid, so 'positively charged' is not a safe generalisation.

**Answer B**
- value: `64`
- verdict: **caveat**, reasons: liquid_dependent
- says: Out of 113 reported zeta-potential values for amine-functionalised polystyrene nanoparticles, 64 are negative (and 49 positive), so the majority are actually negative. These particles are not reliably positively charged; the sign flips depending on the suspension medium (e.g., salt or culture media screen the amine charge), so a blanket 'positively charged' claim is not supported by the data.

Your call: 

## Z2. Across the literature, does the zeta potential of micro- and nanoplastics follow particle size? Give Spearman's rho of log size against zeta.

**Answer A**
- value: `0.02`
- verdict: **allow**, reasons: none
- says: Across 1046 measurements from 278 papers, Spearman's rho between log size and zeta potential is 0.02 (p=0.46), indicating essentially no correlation. Zeta potential does not follow particle size in the literature.

**Answer B**
- value: `-0.07`
- verdict: **caveat**, reasons: composition_shift, method_mix, liquid_dependent, held_twice
- says: Across this compiled literature set, log(size) and zeta potential show only a very weak, near-null Spearman correlation (rho ≈ -0.07), so size is not a reliable predictor of zeta potential. The signal is swamped by differences in surface chemistry (plain/amine/carboxyl/sulfate, which flips the sign) and suspension medium (DI water vs. salt/culture media, which strongly dampens magnitude).

Your call: 

## Z3. Which polymer group has a positive median zeta potential in the literature, and what is that median (mV)? How robust is it?

**Answer A**
- value: `21.77`
- verdict: **caveat**, reasons: single_paper
- says: Nylon microplastics show a positive median zeta potential of about 21.77 mV (n=25 measurements), but 20 of those 25 values come from a single study (PMC9370135), so the finding is not robustly supported across independent papers.

**Answer B**
- value: `21.8`
- verdict: **caveat**, reasons: single_paper
- says: The polymer group with a positive median zeta potential is reported at 21.8 mV (n=25 across 3 papers). However, 20 of these values come from a single paper, so this result should be treated cautiously.

Your call: 

## Z4. What share of papers reporting zeta potentials state the ionic strength for at least one value? Answer as a fraction.

**Answer A**
- value: `0.081`
- verdict: **allow**, reasons: none
- says: About 0.081 (38 out of 467 papers reporting zeta potentials) state the ionic strength for at least one value.

**Answer B**
- value: `0.0814`
- verdict: **allow**, reasons: none
- says: 38 of 467 papers reporting zeta potentials state the ionic strength for at least one value, i.e. 38/467 (~8.1%).

Your call: 

## Z5. Two papers from one lab report -48.7 mV and -14.7 mV for 100 nm polystyrene in 0.3 mM NaCl at pH 7.4 and 25 C on the same instrument (rows PMC10260929-r1 and PMC13298883-r1). May they be compared, and how far apart are they (mV)?

**Answer A**
- value: `34.0`
- verdict: **caveat**, reasons: composition_shift
- says: The two measurements share medium, pH, ionic strength, and temperature, but the measured particle sizes differ substantially (119.5 nm vs 158.1 nm) despite the same 100 nm nominal label, suggesting different particle batches/surface chemistry that likely drive the gap. The difference is 34.0 mV (-48.7 vs -14.7 mV).

**Answer B**
- value: `34.0`
- verdict: **allow**, reasons: none
- says: Yes, the two measurements are comparable since they match in material, size, electrolyte, pH, and temperature on the same instrument. The difference between -48.7 mV and -14.7 mV is 34.0 mV.

Your call: 
