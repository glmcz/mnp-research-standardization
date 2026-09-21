# Cíle projektu a otázky pro vědce

Psáno 2026-09-21, pro Martina, k použití v rozhovoru.

Každé číslo v tomhle dokumentu je změřené na korpusu 858 článků z Europe PMC, z nichž
491 obsahuje aspoň jedno měření. Není tu nic odhadnutého.

---

## Část 1 — co projekt dělá

### Hlavní cíl, jednou větou

Posunout se od **zjištění, že nanoplasty někde jsou**, k **popisu, který umožní výsledky
porovnat mezi studiemi**.

### Proč to vůbec nejde dnes

Tři důvody, každý je v abstraktu:

1. **Různé metody vidí různé velikostní rozsahy.** Dvě studie stejné matrice reportují jiné
   koncentrace, aniž by se lišilo skutečné znečištění. Liší se jen mez detekce metody.
2. **Nanoplasty nejsou jedna třída částic.** Chování určuje velikost, polymer, povrchová
   chemie, stáří a okolní prostředí dohromady, ne jeden parametr.
3. **Zeta potenciál sám nestačí.** Chemicky různé částice konvergují k podobné zetě po vzniku
   proteinové korony, takže podobná zeta neznamená podobné chování.

### Co se z toho staví

| část | co to je | stav |
|---|---|---|
| dataset | 1 890 měření z 491 prací, s podmínkami a s **explicitní nepřítomností** | hotovo |
| schéma | jaké parametry musí být uvedeny, aby šlo měření použít | hotovo |
| převodník | článek → strojově čitelná podoba, kde každý údaj ví, ze kterého řádku pochází | hotovo |
| vyhodnocení | měří, jestli tyhle nástroje AI agentovi vůbec pomáhají | rozestavěno |

**Klíčový rozdíl oproti běžné databázi:** ukládá se i to, co článek **neuvedl**. "Iontová síla
neuvedena" je tvrzení o článku, ověřitelné strojem, ne prázdná buňka.

### Čísla, která můžeš v rozhovoru použít

| tvrzení | číslo |
|---|---|
| prací, kde ani jedno měření nemá všech pět podmínek | **97,4 %** (478 z 491) |
| měření, která mají všech pět podmínek | **2,3 %** (na práci; 3,3 % na řádek) |
| prací, které uvádějí iontovou sílu | **8,7 %** (na práci) |
| prací, které uvedly, jakým modelem převedly mobilitu na zetu | **6,8 %** ze 485 |
| dvojic měření v celém korpusu, které jde skutečně porovnat | **16** z 1 785 105 |
| z toho dvojic zeta-vs-zeta napříč různými pracemi | **0** |

To poslední je nejsilnější věc, kterou máš. **Žádný zeta potenciál v tomhle korpusu nelze
porovnat se zetou z jiné práce.** Ne málo. Nula.

### Kterých pět podmínek, a jak se dnes počítá, že jsou "uvedené"

Tohle je první věc, na kterou se tě vědec zeptá. Měj to po ruce doslova.

| podmínka | proč bez ní zeta nic neznamená | počítá se jako uvedená | nepočítá se |
|---|---|---|---|
| **médium** | zeta je vlastnost částice **a** jejího média | jakékoli pojmenování kapaliny, i "DI water" i "PBS" | článek kapalinu nikdy nepojmenuje |
| **iontová síla** (mM) | určuje Debyeovu délku; bez ní nemá křivka mobility osu x | "10 mM NaCl"; i vytištěné složení ("0,137 M NaCl, 0,0027 M KCl"), pak jako **odvozená** | "PBS" nebo "HEPES" samotné; složka, jejíž speciaci článek neuvádí; **nikdy se nedohledává nominální hodnota** |
| **pH** | určuje disociaci povrchových skupin, u funkcionalizované částice mění i znaménko | číslo, i rozsah ("mezi 6,8 a 7,2") | "fyziologické pH" bez čísla |
| **teplota** (°C) | vstupuje do ε, η a kT v každém modelu | číslo; i "room temperature", ale s příznakem *nominální* | teplota inkubace, expozice, skladování nebo kultivace — **ani když článek jinou neuvádí** |
| **přístroj** | různé přístroje aplikují jiný převod mobility na zetu | i rodina ("Zetasizer"); značka a model je lepší a ukládá se doslova | nic neuvedeno |

**Plně podmíněno** znamená všech pět **současně na jednom řádku**. Proto je to číslo tak nízké.
Jednotlivě to vypadá mnohem líp — médium 72 %, přístroj 81 % — ale průnik spadne na 2,3 %.

**Tři pravidla navíc, která rozhodují víc, než by se zdálo:**

1. **Rozsah platnosti.** Podmínka platí jen uvnitř experimentu, který ji uvádí. Nepřenáší se na
   jinou přípravu, ani když je ve stejném článku. Ratifikováno 13. 9.
2. **Nepřítomnost se nikdy nedoplňuje.** "DI water" neznamená iontová síla nula. Znamená médium
   uvedeno, iontová síla neuvedena. Tohle je jediné pravidlo, jehož zrušení by čísla změnilo
   řádově — ověřeno, pustí 16 srovnatelných dvojic na 81 624.
3. **Všechna čísla jsou horní odhad.** Protože "uvedeno" je měkčí než "uvedeno číslem": rozsah
   pH se počítá, nominální teplota se počítá, rodina přístroje se počítá. Skutečná úplnost je
   tedy ještě nižší než 2,3 %.

---

---

## Část 2 — otázky pro vědce

Seřazeno podle toho, jak moc mi odpověď odblokuje práci. U každé je napsáno,
**proč se ptám** a **co se změní**, abys to uměl obhájit, když se zeptají proč to chceš vědět.

### A. Měřená veličina — co vlastně je podmínka a co výsledek

**A1. Je kritická koagulační koncentrace (CCC) podmínka měření, nebo výsledek?**

*Proč se ptám:* jedna práce uvádí CCC 56 a 398 mM. V datasetu to skončilo jako iontová síla,
při které se měřilo. Ale CCC je nafitovaná hodnota, při které agregace přejde do difúzního
režimu — tedy výstup experimentu, ne jeho nastavení.

*Co se změní:* jestli je to výsledek, nemá to ve sloupci podmínek co dělat. Ale pak nemám kam
to dát, protože schéma pro CCC políčko nemá. Zajímá mě, jestli to má být samostatná veličina.

**A2. Když práce reportuje sérii (1, 10 a 100 mM KCl), jak má vypadat jeden řádek?**

*Proč se ptám:* jedno číslo tam nepatří, protože měření je série. Ale napsat "neuvedeno" je
lež, protože práce to uvedla úplně jasně.

*Co se změní:* uvažuju o textovém poli vedle čísla, jak už to mám u pH a teploty. Chci vědět,
jestli to dává smysl, nebo jestli se série má rozpadnout na víc řádků.

### B. Převod mobility na zetu

**B1. Jen 6,8 % prací uvádí, jestli použily Smoluchowského nebo Hückela. Je to v oboru normální?**

*Proč se ptám:* zeta se neměří, měří se elektroforetická mobilita. Zeta je modelový převod a ty
dva limity se liší faktorem 1,5. Přijde mi divné, že se to skoro nikdy nepíše.

*Co se změní:* pokud obor bere za dané, že přístroj použil svůj default, pak je to reportovací
problém, ne vědecký. Pokud ne, je to vážnější, než jsem myslel.

**B2. Práce, které reportují mobilitu, uvádějí model 46 % případů. Práce, které reportují zetu,
6,8 %. Znamená to něco, nebo je to jen malý vzorek?**

*Proč se ptám:* je to obráceně, než bych čekal. Ten, kdo dá surovou mobilitu, si model můžu
dopočítat sám. Ten, kdo dá zetu, už rozhodl za mě — a právě ten to nepíše.

*Co se změní:* skupina s mobilitou má jen 13 prací, takže si tím nejsem jistý. Chci vědět,
jestli to sedí se zkušeností, nebo jestli to mám z prezentace vyhodit.

### C. Metody detekce a jejich meze

**C1. Jaké jsou v praxi dolní meze metod, a sedí tyhle?**

Mám ve schématu: vizuální třídění 300 µm, FTIR-ATR 500 µm, FTIR zobrazování 10 µm,
Raman 1 µm, Py-GC/MS 1 µm, SEM-EDS 0,1 µm, TEM 1 nm, AFM 1 nm, DLS 1 nm, NTA 10 nm.

*Proč se ptám:* tyhle meze jsou to, co dělá koncentrace mezi studiemi nesrovnatelné, takže
musí být správně.

**C2. Patří Py-GC/MS vůbec do tabulky velikostních mezí?**

*Proč se ptám:* pyrolýza nepočítá částice, měří hmotnost polymeru v plynné fázi. Její mez je
hmotnostní, ne velikostní. Mám pocit, že tím míchám dvě různé veličiny.

*Co se změní:* pokud ano, musím rozlišit "mez v počtu částic" a "mez v hmotnosti", což je
docela zásah do schématu.

**C3. Když práce kombinuje víc metod na identifikaci, jaká je výsledná mez?**

*Proč se ptám:* schéma dnes dovolí jednu metodu na řádek. Když někdo udělá Raman plus
Py-GC/MS, nevím, jestli mám brát horší mez, nebo průnik, nebo to vést jako dvě měření.


### D. Stáří a stav povrchu

**D1. Jak by se mělo zapisovat stáří plastu?**

*Proč se ptám:* stárnutí ovlivňuje elektrostatické chování přes UV, sůl, mechanické namáhání.
V korpusu se zvětrávání zmiňuje v 77 % prací, takže je to zdaleka nejčastější z "skrytých"
parametrů. Ale nevím, jestli se má zapisovat jako doba, jako dávka UV, nebo jen kvalitativně.

**D2. Kontaktní elektrizace a nábojové mozaiky se v korpusu zmiňují v 1,3 % a 0,9 % prací.
Je to proto, že se to neměří, nebo proto, že to u nanoplastů nehraje roli?**

*Proč se ptám:* je to zajímavý mechanismus, ale data pod ním nejsou. Nechci o něm mluvit jako
o něčem změřeném, když v literatuře skoro není.

**D3. Dává smysl brát zeta potenciál jako ukazatel škodlivosti pro organismy?**

*Proč se ptám:* je to můj nápad a nejsem si jím jistý. Abstrakt sám argumentuje, že zeta
nepředpovídá chování. Zajímá mě, jestli jako **jeden vstup z několika** to obstojí, nebo
jestli je to slepá ulička.

### E. Srovnatelnost — pravidla, která jsem musel zvolit

Postavil jsem pravidlo, které pro dvě měření řekne, jestli se dají porovnat. Vyšlo z něj
16 srovnatelných dvojic z 1,78 milionu. Tři rozhodnutí v něm jsou moje a chci je ověřit.

**E1. Jsou tolerance rozumné?** Iontová síla ±10 %, pH ±0,2, teplota ±2 °C.

**E2. Je správné vyžadovat stejný κa režim?** Počítám Debyeovu délku a Henryho funkci a dvě
měření v různých režimech nepovažuju za srovnatelná, i když mají všechno ostatní stejné.

**E3. Debyeovu délku počítám pro 1:1 elektrolyt.** Pro CaCl₂ a fosfáty je to špatně. Jak moc to
vadí, když to používám jen k zařazení do režimu, ne k opravě hodnoty?

### G. Je celý mechanismus standardizace postavený správně?

Tahle skupina je na ověření základů. Ukaž jim konkrétní práci a nech si říct, kde je to špatně.

**G1. Příklad na jedné práci — je takhle správně?** (PMC10141840)

Článek má v tabulce tři měření. Stejná částice, stejné pH, stejná teplota, stejný přístroj.
Mění se **jen médium**:

| médium | zeta |
|---|---|
| H₂O (0,55 µS) | **−67,81 mV** |
| PBS | **−45,89 mV** |
| RPMI-1640 (fs) | **−14,03 mV** |

*Tohle je celý abstrakt v jedné tabulce.* Jedna a tatáž částice má v různých prostředích zetu
lišící se o **54 mV**. Kdo vezme jedno z těch čísel bez média, nenese informaci o částici.

Takhle jsme ty tři řádky standardizovali:

| podmínka | výsledek | proč |
|---|---|---|
| médium | **uvedeno** — `DI_water`, `buffer`, `culture_medium` | článek kapalinu pojmenoval |
| pH | **uvedeno**, 7,4 | stojí v titulku tabulky |
| teplota | **uvedeno**, 25 °C | také v titulku tabulky |
| přístroj | **uvedeno**, Zetasizer Pro (Malvern) | značka i model, doslova |
| **iontová síla** | **NEUVEDENO** u všech tří | a to je ta zajímavá část |

**Iontová síla padla třikrát, pokaždé z jiného důvodu:**

1. `H₂O (0,55 µS)` — článek dal **vodivost**, ne iontovou sílu. Převod existuje, ale potřebuje
   předpoklad o složení. Nepřevádíme.
2. `PBS` — název pufru bez vytištěného složení. Nominální hodnotu PBS zná každý, ale
   nedohledáváme ji. Kdyby článek složení vytiskl, počítalo by se jako **odvozená**.
3. `RPMI-1640 (fs)` — kultivační médium, složení neuvedeno, navíc sérum.

Takže ani jeden ze tří řádků není plně podmíněný, a ani jeden nelze porovnat s ničím mimo
tenhle článek. Přitom je to slušně napsaná práce.

**Zeptej se konkrétně na tohle:**

- Je správné **nepřevádět vodivost na iontovou sílu**? Je to konzervativní, ale možná až moc.
- Je správné **nedohledávat složení PBS**? Nominální hodnotu zná obor. Já to odmítám, protože
  jinak by "neuvedeno" přestalo znamenat "neuvedeno". Souhlasíte?
- Kdybyste tu tabulku četli vy, co byste z ní **bez zbytku článku** ještě uměli použít?

**G2. Re-sampling — je práce ta správná jednotka nezávislosti?**

*Co dělám:* řádky nejsou nezávislé, shlukují se do prací. Medián 2 řádky na práci, maximum 90,
horních 10 % prací drží 41 % dat. Takže počítám procenta **na práci, s váhou 1 na práci**, a
intervaly dělám bootstrapem, kde losuji **práce, ne řádky**. Vnitrotřídní korelace vyšla
0,78–0,94, efektivní velikost vzorku 517–588 místo 1 890.

*Otázky, kde si nejsem jistý:*

- **Je práce správná jednotka, nebo má být laboratoř?** Dvě práce ze stejné skupiny taky
  nejsou nezávislé — sdílejí přístroj, protokol i reportovací zvyky. Jestli ano, moje čísla
  jsou pořád optimistická a skutečné *n* je ještě menší.
- **Má mít každá práce váhu 1?** Nebo se má vážit počtem experimentů, počtem částic, nebo
  něčím jiným? Práce se třemi měřeními a práce s devadesáti mají dnes stejný hlas.
- **Je to vůbec ta správná otázka?** ICC 0,78–0,94 mi říká, že reportování je vlastnost
  laboratoře, ne měření. Jestli je to pravda, popisná statistika napříč pracemi možná měří
  spíš zvyky skupin než stav literatury.

Ta poslední je pro mě nejdůležitější, protože kdyby platila, znamená to, že se má měřit něco
jiného, než měřím.

### F. Otázky, které otevírají rozhovor

Tyhle nemají správnou odpověď. Jsou na to, aby ti řekli, co potřebují.

**F1. Kdyby takový dataset existoval, na co byste ho použili?**

To je nejdůležitější otázka v celém dokumentu. Odpověď rozhodne, co má smysl stavět dál.

**F2. Jaké minimum parametrů musí být uvedeno, aby se dalo měření vůbec použít?**

Mám pět: **médium, iontová síla, pH, teplota, přístroj.** Vyber si z těchhle tří otázek podle
toho, kam se rozhovor stočí:

- **Chybí něco?** Napadá mě velikost měřená v tomtéž médiu, doba od dispergace a protokol
  sonikace. Zatím je nemám a nevím, jestli patří mezi povinné, nebo mezi volitelné.
- **Je něco navíc?** Přístroj je z té pětice nejméně jistý. Beru ho jako zástupný ukazatel
  převodního modelu, protože ten se uvádí jen v 6,8 % prací. Kdyby se model psal přímo,
  přístroj by možná nebyl potřeba.
- **Souhlasíte s tím, co počítám jako "uvedeno"?** Ukaž jim tabulku z části 1. Konkrétně:
  bere se "room temperature" jako uvedená teplota? Stačí "Zetasizer" bez modelu? A je správné
  odmítnout dohledání nominálního složení PBS, i když ho každý zná?

Ta poslední otázka je nejcennější, protože moje definice "uvedeno" určuje **každé** procento
v téhle práci. Když je nastavená jinak, než by ji nastavil obor, jsou všechna čísla vedle.

**F3. Našel jsem práci, která uvádí svou koncentraci soli dvakrát a ta dvě čísla se liší
tisícinásobně. Jak časté to je, a co s tím má dataset dělat?**

*Kontext:* v metodice je 5–30 % hmotnostních, ve výsledcích 0–30 mg/l. Všechny automatické
kontroly to prošly, protože kontradikce je vlastnost dvojice vět a kontroly se dívají na
jednu větu.

**F4. Co by vás na takovém datasetu nejdřív napadlo zpochybnit?**

Ptej se na to na konci. Je to nejlevnější způsob, jak najít díru dřív než recenzent.

---

## Část 3 — co si z rozhovoru odnést

Tři věci, které stojí za zapsání bez ohledu na to, kam se rozhovor stočí:

1. **Jakou otázku by si položili, kdyby data měli.** To je specifikace produktu.
2. **Kterou z mých pěti podmínek považují za nejdůležitější a proč.** Pořadí mi řekne,
   co má smysl doplňovat jako první.
3. **Jestli existuje standard, který už tohle řeší.** Ptej se přímo. Pokud ano, je lepší se
   na něj napojit než stavět vedle.

**Poznámka, kterou je poctivé říct nahlas:** základní pravdu k tomu datasetu anotoval model,
ne člověk, a nezávislý lidský audit zatím proběhl na nule řádků. Všechna čísla o přesnosti
extrakce jsou tím pádem předběžná. Když to řekneš dřív, než se někdo zeptá, je to síla.
Když to vyjde najevo potom, je to díra.
