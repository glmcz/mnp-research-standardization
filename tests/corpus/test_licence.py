"""The licence of a source article, read from its own JATS.

Every `<license>` element below is copied verbatim from the vendored XML named beside it,
because the classifier's job is to read what publishers actually write — and they write it
in at least four shapes: a machine-readable `xlink:href`, an `ali:license_ref`, a URL inside
the prose, and prose with no URL at all.

The two ShareAlike codes are the exception: no paper in the corpus carries one, so those
statements are built from a real one with only the licence name changed, and say so.
"""

import subprocess
import sys

import pandas as pd
import pytest

from mnp import config
from mnp.corpus import licence

XLINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'
ALI = 'xmlns:ali="http://www.niso.org/schemas/ali/1.0/"'


def _xml(license_xml: str, extra: str = "") -> bytes:
    return (
        f'<?xml version="1.0"?><article {XLINK} {ALI}><front><article-meta>'
        f"<permissions>{license_xml}</permissions></article-meta></front>{extra}"
        "<body/></article>"
    ).encode()


# PMC11644253 — MDPI: the URL is in ali:license_ref and again in an ext-link.
MDPI_URL = (
    '<license><ali:license_ref specific-use="textmining" content-type="ccbylicense">'
    "https://creativecommons.org/licenses/by/4.0/</ali:license_ref><license-p>Licensee MDPI, "
    "Basel, Switzerland. This article is an open access article distributed under the terms "
    "and conditions of the Creative Commons Attribution (CC BY) license (<ext-link "
    'ext-link-type="uri" xlink:href="https://creativecommons.org/licenses/by/4.0/">'
    "https://creativecommons.org/licenses/by/4.0/</ext-link>).</license-p></license>"
)
# PMC12261319 — ACS: no URL anywhere, the code named in words.
ACS_CC_BY_WORDS = (
    "<license><license-p>This article is licensed under CC-BY 4.0</license-p></license>"
)
# PMC10664492 — Springer/BMC: the article is CC BY; the CC0 waiver covers only the data.
BMC_BY_PLUS_DATA_WAIVER = (
    "<license><license-p><bold>Open Access</bold> This article is licensed under a Creative "
    "Commons Attribution 4.0 International License, which permits use, sharing, adaptation, "
    "distribution and reproduction in any medium or format, as long as you give appropriate "
    "credit to the original author(s) and the source, provide a link to the Creative Commons "
    "licence, and indicate if changes were made. To view a copy of this licence, visit "
    '<ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/" ext-link-type="uri">'
    "http://creativecommons.org/licenses/by/4.0/</ext-link>. The Creative Commons Public "
    "Domain Dedication waiver (<ext-link xlink:href="
    '"https://creativecommons.org/publicdomain/zero/1.0/" ext-link-type="uri">'
    "http://creativecommons.org/publicdomain/zero/1.0/</ext-link>) applies to the data made "
    "available in this article, unless otherwise stated in a credit line to the data."
    "</license-p></license>"
)
# PMC7373282 — PLOS: CC0 on the article; its sub-articles carry CC BY of their own.
PLOS_CC0 = (
    '<license xlink:href="https://creativecommons.org/publicdomain/zero/1.0/">'
    '<ali:license_ref specific-use="textmining" content-type="cc0license">'
    "https://creativecommons.org/publicdomain/zero/1.0/</ali:license_ref><license-p>This is an "
    "open access article, free of all copyright, and may be freely reproduced, distributed, "
    "transmitted, modified, built upon, or otherwise used by anyone for any lawful purpose. "
    'The work is made available under the <ext-link ext-link-type="uri" '
    'xlink:href="https://creativecommons.org/publicdomain/zero/1.0/">Creative Commons CC0'
    "</ext-link> public domain dedication.</license-p></license>"
)
PLOS_SUB_ARTICLE = (
    "<sub-article><front-stub><permissions>"
    '<license xlink:href="http://creativecommons.org/licenses/by-nc/4.0/"><license-p>'
    "sub-article licence</license-p></license></permissions></front-stub></sub-article>"
)
# PMC10450312 — SAGE: the URL in an ext-link, a non-CC URL beside it.
SAGE_BY_NC = (
    "<license><license-p>This article is distributed under the terms of the Creative Commons "
    'Attribution-NonCommercial 4.0 License (<ext-link xlink:href="https://creativecommons.org/'
    'licenses/by-nc/4.0/" ext-link-type="uri">https://creativecommons.org/licenses/by-nc/4.0/'
    "</ext-link>) which permits non-commercial use, reproduction and distribution of the work "
    "without further permission provided the original work is attributed as specified on the "
    'SAGE and Open Access page (<ext-link xlink:href="https://us.sagepub.com/en-us/nam/'
    'open-access-at-sage" ext-link-type="uri">https://us.sagepub.com/en-us/nam/'
    "open-access-at-sage</ext-link>).</license-p></license>"
)
# PMC12281096 — RSC: the licence name is the link text, the URL only in its href.
RSC_BY_NC_WORDS_AND_HREF = (
    '<license><license-p>This article is licensed under a <ext-link xlink:href="https://'
    'creativecommons.org/licenses/by-nc/3.0/" ext-link-type="uri">Creative Commons '
    "Attribution-Non Commercial 3.0 Unported Licence</ext-link>. You can use material from "
    "this article in other publications without requesting further permissions from the RSC, "
    "provided that the correct acknowledgement is given and it is not used for commercial "
    "purposes.</license-p></license>"
)
# PMC12319994-style RSC statement with the href stripped: wording alone must still say NC.
RSC_BY_NC_WORDS_ONLY = (
    "<license><license-p>This article is licensed under a Creative Commons Attribution-Non "
    "Commercial 3.0 Unported Licence. You can use material from this article in other "
    "publications without requesting further permissions from the RSC, provided that the "
    "correct acknowledgement is given and it is not used for commercial purposes."
    "</license-p></license>"
)
# PMC10340104 — OUP: prose names no licence at all, the URL decides.
OUP_BY_NC_ND = (
    "<license><license-p>Permits non-commercial access and re-use, provided that author "
    "attribution and integrity are maintained; but does not permit creation of adaptations or "
    'other derivative works (<ext-link xlink:href="https://creativecommons.org/licenses/'
    'by-nc-nd/4.0/" ext-link-type="uri">https://creativecommons.org/licenses/by-nc-nd/4.0/'
    "</ext-link>).</license-p></license>"
)
# PMC12645312 — ACS, words only.
ACS_BY_NC_ND_WORDS = (
    "<license><license-p>This article is licensed under CC-BY-NC-ND 4.0</license-p></license>"
)
# PMC7009542 — Wiley: the only CC BY-ND in the corpus.
WILEY_BY_ND = (
    "<license><license-p>This is an open access article under the terms of the <ext-link "
    'xlink:href="https://creativecommons.org/licenses/by-nd/4.0/" ext-link-type="uri">'
    "http://creativecommons.org/licenses/by-nd/4.0/</ext-link> License, which permits use and "
    "distribution in any medium, provided the original work is properly cited and no "
    "modifications or adaptations are made.</license-p></license>"
)
# Constructed — no ShareAlike paper exists in the corpus. PMC7009542's shape, code changed.
BY_SA_CONSTRUCTED = WILEY_BY_ND.replace("by-nd/4.0", "by-sa/4.0")
BY_NC_SA_CONSTRUCTED = (
    "<license><license-p>This article is licensed under a Creative Commons "
    "Attribution-NonCommercial-ShareAlike 4.0 International License.</license-p></license>"
)
# PMC10081693 — EHP: public domain, but "unless otherwise noted".
EHP_PUBLIC_DOMAIN = (
    "<license><license-p><italic>EHP</italic> is an open-access journal published with "
    "support from the National Institute of Environmental Health Sciences, National Institutes "
    "of Health. All content is public domain unless otherwise noted.</license-p></license>"
)
# PMC7331029 — ACS AuthorChoice, a publisher licence and a non-commercial one.
ACS_AUTHORCHOICE = (
    "<license><license-p>This is an open access article published under an ACS AuthorChoice "
    '<ext-link ext-link-type="uri" xlink:href="http://pubs.acs.org/page/policy/'
    'authorchoice_termsofuse.html">License</ext-link>, which permits copying and '
    "redistribution of the article or any adaptations for non-commercial purposes."
    "</license-p></license>"
)
# PMC3133525 — permissive-sounding, but names no licence.
UNNAMED_NONCOMMERCIAL = (
    "<license><license-p>This is an Open Access article which permits unrestricted "
    "noncommercial use, provided the original work is properly cited.</license-p></license>"
)


@pytest.mark.parametrize(
    ("statement", "code", "basis"),
    [
        (MDPI_URL, "CC-BY", "url"),
        (ACS_CC_BY_WORDS, "CC-BY", "wording"),
        (BMC_BY_PLUS_DATA_WAIVER, "CC-BY", "url"),
        (PLOS_CC0, "CC0", "url"),
        (SAGE_BY_NC, "CC-BY-NC", "url"),
        (RSC_BY_NC_WORDS_AND_HREF, "CC-BY-NC", "url"),
        (RSC_BY_NC_WORDS_ONLY, "CC-BY-NC", "wording"),
        (OUP_BY_NC_ND, "CC-BY-NC-ND", "url"),
        (ACS_BY_NC_ND_WORDS, "CC-BY-NC-ND", "wording"),
        (WILEY_BY_ND, "CC-BY-ND", "url"),
        (BY_SA_CONSTRUCTED, "CC-BY-SA", "url"),
        (BY_NC_SA_CONSTRUCTED, "CC-BY-NC-SA", "wording"),
        (EHP_PUBLIC_DOMAIN, "other-named", "unclassified"),
        (ACS_AUTHORCHOICE, "other-named", "unclassified"),
        (UNNAMED_NONCOMMERCIAL, "other-named", "unclassified"),
    ],
)
def test_real_statements_classify(statement, code, basis):
    got = licence.classify(_xml(statement))
    assert (got.code, got.basis) == (code, basis)
    assert got.code in licence.CODES


def test_no_licence_element_is_none_not_other():
    """PMC10295233 — RSC: a copyright line, no licence. Nothing was granted, so nothing named."""
    xml = (
        b'<?xml version="1.0"?><article><front><article-meta><permissions><copyright-statement>'
        b"This journal is \xc2\xa9 The Royal Society of Chemistry</copyright-statement>"
        b"</permissions></article-meta></front><body/></article>"
    )
    got = licence.classify(xml)
    assert got.code == "none"
    assert not got.quote_allowed


def test_a_sub_article_licence_is_not_the_articles():
    """PMC7373282: CC0 on the article, CC BY-NC here on a sub-article. The article's wins."""
    assert licence.classify(_xml(PLOS_CC0, extra=PLOS_SUB_ARTICLE)).code == "CC0"
    only_sub = _xml("", extra=PLOS_SUB_ARTICLE)
    assert licence.classify(only_sub).code == "none"


def test_a_url_that_contradicts_its_own_wording_is_not_trusted():
    """The URL is preferred, but a statement that says two things is not certain of either."""
    contradicting = MDPI_URL.replace(
        "Creative Commons Attribution (CC BY)", "Creative Commons Attribution-NonCommercial"
    )
    assert licence.classify(_xml(contradicting)).code == "other-named"


def test_two_different_licence_urls_are_ambiguous():
    two = SAGE_BY_NC.replace(
        "</license-p>", " See also creativecommons.org/licenses/by/4.0/</license-p>"
    )
    assert licence.classify(_xml(two)).code == "other-named"


def test_only_cc_by_and_cc0_allow_a_quote():
    allowed = {c for c in licence.CODES if licence.Licence(c, "url", "").quote_allowed}
    assert allowed == {"CC-BY", "CC0"}


def test_the_statement_is_kept_for_the_report():
    got = licence.classify(_xml(ACS_AUTHORCHOICE))
    assert "ACS AuthorChoice" in got.statement


# --- the vendored corpus ----------------------------------------------------------------


@pytest.fixture
def dataset_pmcids():
    table = config.ROOT / "out" / "tables" / "d1_zeta_table.csv"
    if not table.is_file() or not any(config.EPMC_XML_DIR.glob("PMC*.xml")):
        pytest.skip("no corpus restored here")
    return sorted(pd.read_csv(table)["pmcid"].unique())


def test_every_dataset_paper_gets_a_code_from_its_vendored_xml(dataset_pmcids):
    codes = {p: licence.read(p).code for p in dataset_pmcids}
    assert set(codes.values()) <= set(licence.CODES)
    assert len(codes) == len(dataset_pmcids)


def test_the_classifier_reads_nothing_gitignored(dataset_pmcids):
    """A fresh clone has the tarball, not `data/interim/articles.parquet`.

    Run in a clean interpreter with an audit hook on every file open: whatever the classifier
    touches under the repository must be either tracked by git or one of the XMLs that
    `corpus restore` unpacks from the tracked archive — listed in the tracked manifest.
    """
    sample = dataset_pmcids[:: max(1, len(dataset_pmcids) // 40)]
    code = (
        "import sys, json\n"
        "opened = []\n"
        "sys.addaudithook(lambda e, a: opened.append(str(a[0])) if e == 'open' and "
        "isinstance(a[0], str) else None)\n"
        "from mnp.corpus import licence\n"
        "del opened[:]\n"
        "for p in sys.argv[1:]:\n"
        "    licence.read(p)\n"
        "print(json.dumps(sorted(set(opened))))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, *sample],
        capture_output=True,
        text=True,
        check=True,
        cwd=config.ROOT,
    )
    import json

    opened = [p for p in json.loads(done.stdout.strip().splitlines()[-1])]
    root = str(config.ROOT) + "/"
    inside = [p[len(root) :] for p in opened if p.startswith(root)]
    assert inside, "the classifier opened no file at all — the audit hook saw nothing"
    manifest = (config.EPMC_XML_DIR.parent / "manifest.sha256").read_text()
    vendored = {line.split()[-1] for line in manifest.splitlines() if line.strip()}
    xml_prefix = config.EPMC_XML_DIR.relative_to(config.ROOT).as_posix() + "/"
    for rel in inside:
        if rel.startswith(xml_prefix):
            assert rel[len(xml_prefix) :] in vendored or rel in vendored, rel
            continue
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", rel], cwd=config.ROOT, check=False
        ).returncode
        assert ignored != 0, f"the classifier read a gitignored file: {rel}"
