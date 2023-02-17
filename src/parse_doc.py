"""Analyse le document dans son ensemble.

Extrait des empans de texte correspondant aux en-têtes, pieds-de-page,
autorité, vus, correspondants, articles, signature...
"""

from pathlib import Path
import re
from typing import Optional, Tuple

import pandas as pd  # tableau récapitulatif des extractions

from actes import P_STAMP  # tampon
from doc_template import P_HEADER, P_FOOTER  # en-tête et pied-de-page
from separate_pages import load_pages_text
from text_structure import (
    P_ARR_NUM,
    P_ARR_OBJET,
    RE_MAIRE_COMMUNE,
    P_MAIRE_COMMUNE,
    RE_VU,
    P_VU,
    RE_CONSIDERANT,
    P_CONSIDERANT,
)

# type de données des colonnes du fichier CSV résultat
DTYPE_PARSES = {
    # doc
    "filename": "string",
    # page
    "page_num": "int64",
    # pour chaque empan repéré: position et texte
    "span_beg": "int64",
    "span_end": "int64",
    "span_txt": "string",
    "span_typ": "string",  # header, footer, ...  # TODO ensemble fermé?
}


# Marseille: PDF texte, dans lesquels les articles du code de la construction et de l'habitation sont ajoutés en annexe
# *sous forme d'images*


def parse_page_template(txt: str) -> Tuple[list, str]:
    """Analyse une page pour repérer le template.

    Repère les en-têtes, pieds-de-page, tampons.

    Parameters
    ----------
    txt: str
        Texte d'origine de la page.

    Returns
    -------
    content: list
        Liste d'empans repérés sur la page.
    txt_body: string
        Corps de texte, défini comme le texte en entrée
        dans lequel les empans d'en-têtes, pieds-de-page et tampons
        de `content` ont été effacés (remplacés par des espaces de
        même longueur).
    """
    content = []

    # en-tête
    # TODO expectation: n=0..2 par page
    if m_headers := P_HEADER.finditer(txt):
        for match in m_headers:
            content.append(
                {
                    "span_beg": match.span()[0],
                    "span_end": match.span()[1],
                    "span_txt": match.group(0),
                    "span_typ": "header",
                }
            )

    # pied-de-page
    # TODO expectation: n=0..2 par page
    if m_footers := P_FOOTER.finditer(txt):
        for match in m_footers:
            content.append(
                {
                    "span_beg": match.span()[0],
                    "span_end": match.span()[1],
                    "span_txt": match.group(0),
                    "span_typ": "footer",
                }
            )

    # tampon de transmission à actes
    if m_stamps := P_STAMP.finditer(txt):
        for match in m_stamps:
            m_beg, m_end = match.span()
            content.append(
                {
                    "span_beg": m_beg,
                    "span_end": m_end,
                    "span_txt": match.group(0),
                    "span_typ": "stamp",
                }
            )

    # corps du texte
    # défini comme le texte d'origine, dans lequel on a effacé les empans repérés
    # (en-têtes, pieds-de-page, tampons) ;
    # remplacer les empans par des espaces permet de conserver les indices d'origine
    # et éviter les décalages
    spans = list((x["span_beg"], x["span_end"]) for x in content)
    txt_body = txt[:]
    for sp_beg, sp_end in spans:
        txt_body = txt_body[:sp_beg] + " " * (sp_end - sp_beg) + txt_body[sp_end:]

    return content, txt_body


# motif pour capturer tout le texte sauf les espaces initiaux et finaux
RE_STRIP = r"""(?:\s*)(?P<outstrip>\S[\s\S]*?)(?:\s*)"""
P_STRIP = re.compile(RE_STRIP, re.IGNORECASE | re.MULTILINE)


def parse_page_content(
    txt_body: str, page_num: int, latest_span: Optional[dict]
) -> list:
    """Analyse une page pour repérer les zones de contenus.

    Parameters
    ----------
    txt_body: string
        Corps de texte de la page à analyser
    page_num: int
        Numéro de la page
    latest_span: dict
        Dernier empan de contenu repéré sur la page précédente

    Returns
    -------
    content: list
        Liste d'empans de contenu
    """
    content = []
    # page 1
    if page_num == 1:
        # TODO condition suffisante, ou faut-il définir un critère pour gérer des cas marginaux?
        # eg. page avec des métadonnées avant la p. 1
        #
        # repérer le 1er "Vu", et traiter tout ce qui est avant
        if m_vu := P_VU.search(txt_body):
            pream_beg = 0
            pream_end = m_vu.start()
            # a. ce préambule se termine par l'intitulé de l'autorité prenant l'arrêté (obligatoire)
            if match := P_MAIRE_COMMUNE.search(txt_body, pream_beg, pream_end):
                # toute la zone reconnue
                span_beg, span_end = match.span()
                content.append(
                    {
                        "span_beg": span_beg,
                        "span_end": span_end,
                        "span_txt": match.group(0),
                        "span_typ": "par_autorite",
                    }
                )
                autorite_beg = span_beg  # la zone restant à traiter est avant cette zone d'autorité
                # vérifier que la zone de l'autorité est bien en fin de préambule
                try:
                    assert txt_body[span_end:pream_end].strip() == ""
                except AssertionError:
                    print(txt_body[span_end:pream_end].strip())
                    raise
                # stocker la donnée de la commune
                content.append(
                    {
                        "span_beg": match.start("commune"),
                        "span_end": match.end("commune"),
                        "span_txt": match.group("commune"),
                        "span_typ": "adr_ville",  # TODO utiliser un autre nom pour éviter le conflit?
                    }
                )
            else:
                # pas d'autorité détectée: anormal
                autorite_beg = pream_end
                raise ValueError("Pas d'autorité détectée !?")

            # b. ce préambule peut contenir le numéro de l'arrêté (si présent, absent dans certaines communes)
            if match := P_ARR_NUM.search(txt_body, pream_beg, autorite_beg):
                # marquer toute la zone reconnue (contexte + numéro de l'arrêté)
                span_beg, span_end = match.span()
                content.append(
                    {
                        "span_beg": span_beg,
                        "span_end": span_end,
                        "span_txt": match.group(0),
                        "span_typ": "par_arr_num",  # paragraphe contenant le numéro de l'arrêté
                    }
                )
                # stocker le numéro de l'arrêté
                content.append(
                    {
                        "span_beg": match.start("arr_num"),
                        "span_end": match.end("arr_num"),
                        "span_txt": match.group("arr_num"),
                        "span_typ": "arr_num",
                    }
                )
                arr_num_end = span_end
            else:
                # pas de numéro d'arrêté (ex: Aubagne)
                arr_num_end = 0

            # c. entre les deux doit se trouver le titre ou objet de l'arrêté (obligatoire)
            if match := P_ARR_OBJET.search(txt_body, arr_num_end, autorite_beg):
                # stocker la zone reconnue
                content.append(
                    {
                        "span_beg": match.start(),
                        "span_end": match.end(),
                        "span_txt": match.group(0),
                        "span_typ": "par_arr_nom",
                    }
                )
                # stocker la donnée
                content.append(
                    {
                        "span_beg": match.start("arr_nom"),
                        "span_end": match.end("arr_nom"),
                        "span_txt": match.group("arr_nom"),
                        "span_typ": "arr_nom",
                    }
                )
            else:
                # hypothèse: sans marquage explicite comme "Objet:", le titre est tout le texte restant
                # dans cette zone (entre le numéro et l'autorité)
                if match := P_STRIP.fullmatch(txt_body, arr_num_end, autorite_beg):
                    # stocker la zone reconnue
                    content.append(
                        {
                            "span_beg": match.start(),
                            "span_end": match.end(),
                            "span_txt": match.group(0),
                            "span_typ": "par_arr_nom",
                        }
                    )
                    # stocker la donnée
                    content.append(
                        {
                            "span_beg": match.start("outstrip"),
                            "span_end": match.end("outstrip"),
                            "span_txt": match.group("outstrip"),
                            "span_typ": "arr_nom",
                        }
                    )
                else:
                    raise ValueError(
                        f"Pas de texte trouvé pour le nom!?\n{txt_body[arr_num_end:autorite_beg]}"
                    )

            # WIP
            print(content)
        else:
            # RESUME HERE: il ne faut pas traiter les documents vides
            raise ValueError(f"Pas de Vu en p.1 !?\n{txt_body}")
    # RESUME HERE: écrire la logique de repérage de: vu, considérant, arrête, articles
    return content


def parse_arrete(fp_txt_in: Path) -> list:
    """Analyse un arrêté pour le découper en zones.

    Parameters
    ----------
    fp_txt_in: Path
        Fichier texte à analyser.

    Returns
    -------
    doc_content: List[dict]
        Contenu du document, par page découpée en zones de texte.
    """
    doc_content = []  # valeur de retour
    # métadonnées du document
    mdata_doc = {
        "filename": fp_txt_in.name,
    }
    print(fp_txt_in.name)  # DEBUG
    # traiter les pages
    pages = load_pages_text(fp_txt_in)
    latest_span = None  # init
    for i, page in enumerate(pages, start=1):
        mdata_page = mdata_doc | {"page_num": i}
        pg_template, pg_txt_body = parse_page_template(page)
        pg_content = parse_page_content(pg_txt_body, i, latest_span)
        # RESUME HERE
        # TODO latest_span = ... (pour l'itération suivante)
        page_content = mdata_page | {
            "template": pg_template,
            "body": pg_txt_body,
            "content": pg_content,
        }
        doc_content.append(page_content)
    return doc_content
    # WIP
    m_preambule = P_PREAMBULE.search(txt)
    if m_preambule is not None:
        print(fp_txt_in.name, "\tPREAMBULE ", m_preambule)
    else:
        for line in txt.split("\n"):
            m_autorite = P_MAIRE_COMMUNE.match(line)
            if m_autorite is not None:
                print(fp_txt_in.name, "\tAUTORITE  ", m_autorite)
                break
        else:
            raise ValueError(f"{fp_txt_in.name}")
    # end WIP
    # chercher le point de référence "ARRETE|ARRÊTE|ARRÊTONS"
    m_arrete = P_ARRETE.search(txt)
    if m_arrete is not None:
        content["arrete"] = m_arrete.groups()
    else:
        print(repr(txt))
        raise ValueError(f"{fp_txt_in.name}:\t !?")
    # avant ARRETE, on trouve l'en-tête, l'objet, l'autorité, les "vu" et les "considérant"
    # entete
    # objet
    # autorite
    m_autorite = P_MAIRE_COMMUNE.search(txt)
    if m_autorite is not None:
        content["autorite"] = m_autorite.group(0)
    # vus
    m_vu = P_VU.findall(txt)
    content["vu"] = m_vu
    # considerants
    m_considerant = P_CONSIDERANT.findall(txt)
    content["considerant"] = m_considerant
    if not m_considerant:
        if fp_txt_in.name not in (
            "99_AR-013-211300058-20220131-310122_01-AR-1-1_1 (1).txt",  # mainlevée => optionnel ?
            "99_AR-013-211300058-20220318-180322_01-AR-1-1_1.txt",  # mainlevée => optionnel ?
        ):
            raise ValueError(fp_txt_in.name)
    # articles
    # pieddepage
    return content


if __name__ == "__main__":
    # TODO argparse
    INT_TXT_DIR = Path("../data/interim/txt")
    CSV_PARSES = Path("../data/interim") / "parses.csv"
    # stocker les champs extraits dans un tableau
    parses = []
    for fp_txt in sorted(INT_TXT_DIR.glob("*.txt")):
        content = parse_arrete(fp_txt)
        parses.extend(content)
    df_parses = pd.DataFrame(parses)
    # on force les types de colonnes (impossible dans le constructeur...)
    df_parses = df_parses.astype(DTYPE_PARSES)
    # TODO tests: dropna() puis:
    # assert header_beg == 0
    # alt: assert txt[:header_beg] == ""
    # assert footer_end == len(txt)
    # alt: assert txt[footer_end:] == ""
    df_parses.to_csv(CSV_PARSES, index=False)
