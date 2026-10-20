"""Job languages a run can filter on.

A job matches the picked languages in one of two ways:

1. The posting names the languages it requires ("fluent in English",
   "Nederlandstalig", "Deutschkenntnisse"). Every required language must be
   one of the picked ones; for "Dutch or French" one of the two is enough.
   Languages that are only a plus ("French is an asset") do not count.
2. It names none. Then the language the posting is written in must be picked.

Jobs whose text is too short to tell (title-only email alerts) are kept, so
the filter never drops a job just because there was nothing to read.
"""
import html
import re

# id: label, words that name the language (in several languages), stopwords for detection.
_LANGUAGES = [
    ("en", "English",
     ["english", "engels", "engelstalig", "anglais", "anglophone", "englisch", "englischkenntnisse", "inglés",
      "ingles", "inglese", "inglês", "engelska", "engelsk", "englanti", "angielski"],
     ["the", "and", "of", "to", "with", "for", "you", "our", "are", "will", "your", "this", "that",
      "be", "have", "an", "as", "on", "at", "or", "from", "who", "what", "about", "skills", "experience",
      "working", "work", "join", "looking", "role", "can", "within"]),
    ("nl", "Dutch",
     ["dutch", "flemish", "nederlands", "nederlandstalig", "vlaams", "néerlandais", "neerlandais",
      "néerlandophone", "neerlandophone", "niederländisch", "niederlaendisch", "holländisch", "holandés",
      "olandese", "holandês", "nederländska", "hollandsk", "hollanti", "niderlandzki"],
     ["de", "het", "een", "en", "van", "je", "jij", "wij", "met", "voor", "zijn", "bent", "onze", "ons", "naar",
      "bij", "ook", "niet", "dat", "die", "wordt", "hebt", "heb", "om", "te", "op", "als", "jouw", "ervaring",
      "functie", "wat", "kennis", "binnen", "werken"]),
    ("fr", "French",
     ["french", "frans", "franstalig", "français", "francais", "francophone", "französisch", "franzoesisch",
      "francés", "frances", "francese", "francês", "franska", "fransk", "ranska", "francuski"],
     ["le", "la", "les", "des", "du", "et", "un", "une", "pour", "avec", "vous", "nous", "est", "sur", "dans",
      "au", "aux", "votre", "notre", "qui", "que", "être", "expérience", "poste", "vos", "nos", "êtes", "sont",
      "cette", "ce", "par", "connaissance"]),
    ("de", "German",
     ["german", "duits", "duitstalig", "allemand", "germanophone", "deutsch", "deutschkenntnisse",
      "alemán", "aleman", "tedesco", "alemão", "tyska", "tysk", "saksa", "niemiecki"],
     ["der", "die", "das", "und", "ist", "mit", "für", "sie", "wir", "du", "ein", "eine", "den", "dem", "von",
      "zu", "auf", "bei", "unser", "unsere", "ihre", "oder", "nicht", "auch", "erfahrung", "kenntnisse", "deine",
      "dich", "uns", "sind", "werden", "aufgaben"]),
    ("es", "Spanish",
     ["spanish", "spaans", "espagnol", "spanisch", "español", "espanol", "castellano", "spagnolo", "espanhol",
      "spanska", "spansk", "espanja", "hiszpański"],
     ["el", "los", "las", "y", "del", "con", "para", "por", "una", "es", "se", "su", "nuestro", "nuestra",
      "experiencia", "tu", "como", "más", "trabajo", "buscamos", "conocimientos", "equipo"]),
    ("it", "Italian",
     ["italian", "italiaans", "italien", "italienisch", "italiano", "italiana", "italienska", "italiensk", "włoski"],
     ["il", "lo", "gli", "di", "della", "delle", "che", "con", "per", "è", "sono", "nostro", "nostra",
      "esperienza", "nel", "nella", "alla", "dei", "una", "anche", "lavoro", "conoscenza"]),
    ("pt", "Portuguese",
     ["portuguese", "portugees", "portugais", "portugiesisch", "portugués", "portoghese", "português",
      "portugues", "portugisiska", "portugisisk", "portugali", "portugalski"],
     ["os", "do", "da", "dos", "das", "em", "com", "para", "um", "uma", "é", "não", "nosso", "nossa",
      "experiência", "você", "na", "no", "ao", "como", "trabalho", "conhecimento", "equipe"]),
    ("sv", "Swedish",
     ["swedish", "zweeds", "suédois", "suedois", "schwedisch", "sueco", "svedese", "svenska", "svensk",
      "ruotsi", "szwedzki"],
     ["och", "att", "det", "som", "är", "på", "med", "för", "av", "till", "vi", "du", "har", "inte", "om",
      "eller", "vår", "vårt", "erfarenhet", "dig", "oss", "ska", "kommer", "hos", "arbete"]),
    ("da", "Danish",
     ["danish", "deens", "danois", "dänisch", "danés", "danese", "dinamarquês", "danska", "dansk", "tanska",
      "duński"],
     ["og", "at", "det", "som", "er", "på", "med", "af", "til", "vi", "du", "har", "ikke", "eller", "vores",
      "erfaring", "dig", "os", "skal", "hos", "arbejde", "også", "være"]),
    ("no", "Norwegian",
     ["norwegian", "noors", "norvégien", "norvegien", "norwegisch", "noruego", "norvegese", "norueguês",
      "norska", "norsk", "norja", "norweski"],
     ["og", "å", "det", "som", "er", "på", "med", "av", "til", "vi", "du", "har", "ikke", "eller", "vår",
      "erfaring", "deg", "oss", "skal", "hos", "arbeid", "også", "være"]),
    ("fi", "Finnish",
     ["finnish", "fins", "finnois", "finnisch", "finlandés", "finlandese", "finlandês", "finska", "finsk",
      "suomi", "suomen", "fiński"],
     ["ja", "on", "että", "tai", "kanssa", "olet", "meidän", "sinä", "me", "työ", "kokemus", "sekä", "voit",
      "meillä", "sinulla", "olla", "osaamista", "tehtävä"]),
    ("pl", "Polish",
     ["polish", "pools", "polonais", "polnisch", "polaco", "polacco", "polonês", "polsk", "puola", "polski",
      "polskiego"],
     ["i", "w", "z", "na", "do", "się", "jest", "oraz", "dla", "nie", "że", "jako", "doświadczenie", "lub",
      "znajomość", "pracy", "będzie", "naszego", "twoje"]),
]

LANGUAGES = {code: {"id": code, "label": label} for code, label, _names, _stopwords in _LANGUAGES}
_NAME_TO_CODE = {name: code for code, _label, names, _stopwords in _LANGUAGES for name in names}
_STOPWORDS = {code: set(stopwords) for code, _label, _names, stopwords in _LANGUAGES}

# Words that turn a language mention into a requirement, in the languages job posts are usually written in.
_REQUIRED_CUES = [
    "fluent", "fluency", "fluently", "proficient", "proficiency", "native", "mother tongue", "required",
    "requirement", "must", "mandatory", "essential", "speak", "speaking", "spoken", "written", "verbal",
    "command of", "knowledge of", "level", "c1", "c2", "b2", "bilingual", "language", "languages",
    "vloeiend", "kennis", "spreekt", "spreek", "beheersing", "beheerst", "taal", "talen", "moedertaal",
    "vereist", "noodzakelijk", "courant", "maîtrise", "maitrise", "maîtrisez", "parlé", "parle", "écrit",
    "langue", "langues", "bilingue", "exigé", "exige", "requis", "indispensable", "obligatoire",
    "fließend", "fliessend", "sehr gute", "gute", "kenntnisse", "sprache", "sprachen", "verhandlungssicher",
    "muttersprache", "muttersprachler", "voraussetzung", "zwingend", "flytande", "flydende", "flytende",
    "språk", "sprog", "kielitaito", "biegła", "biegły", "fluido", "fluente", "dominio", "madrelingua",
]
# Words that make it only a plus.
_OPTIONAL_CUES = [
    "plus", "bonus", "asset", "advantage", "advantageous", "nice to have", "nice-to-have", "preferred",
    "preferably", "desirable", "beneficial", "is welcome", "would be great", "pluspunt", "troef", "meerwaarde",
    "voordeel", "pré", "atout", "un plus", "souhaité", "souhaitable", "apprécié", "von vorteil", "wünschenswert",
    "wuenschenswert", "vorteilhaft", "meriterande", "merit", "fördel", "fordel", "eduksi", "deseable",
    "gradito", "gradita", "mile widziany", "mile widziana",
]
# Words that offer a choice between two language mentions ("Dutch or French").
_ALTERNATIVE = re.compile(r"(?:\bor\b|\bof\b|\bou\b|\boder\b|\bo\b|\beller\b|\btai\b|\blub\b|/)")
_SENTENCE_SPLIT = re.compile(r"[.;!?\n•·▪●•]+|\s-\s")
_CLAUSE_SPLIT = re.compile(r"[,()]|\bbut\b|\bmaar\b|\bmais\b|\baber\b")
_TAG = re.compile(r"<[^>]+>")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Whole words of two or more letters; tokens glued to digits ("Walters3.6", tracking ids) are skipped.
_WORD = re.compile(r"(?<![\w-])[^\W\d_]{2,}(?:-[^\W\d_]+)?(?![\w-])", re.UNICODE)
_NAME_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(sorted((re.escape(name) for name in _NAME_TO_CODE), key=len, reverse=True))
    + r")(?:[-\s]?(?:speaking|sprachig|talig|language))?(?![\w])",
    re.IGNORECASE,
)
# Names that already say "a speaker of": "Nederlandstalig", "francophone", "Deutschkenntnisse".
_SELF_REQUIRING = {"nederlandstalig", "franstalig", "duitstalig", "engelstalig", "francophone", "anglophone",
                   "germanophone", "néerlandophone", "neerlandophone", "deutschkenntnisse", "englischkenntnisse"}

MIN_DETECTION_WORDS = 8
# Running text is roughly a third function words; alert snippets and metadata are far below this.
MIN_STOPWORD_SHARE = 0.12


def get(code):
    return LANGUAGES.get(str(code).strip().lower())


def public_catalog():
    return list(LANGUAGES.values())


def _plain_text(text):
    text = _URL.sub(" ", _TAG.sub(" ", html.unescape(text or "")))
    return text.replace("*", " ").replace("_", " ")


def _has_cue(text, cues):
    return any(re.search(r"(?<![\w])" + re.escape(cue) + r"(?![\w])", text) for cue in cues)


def required_languages(text):
    """Groups of languages the posting requires; a group is met when any of its languages is picked.

    "Fluent in English and Dutch" gives [{"en"}, {"nl"}]; "Dutch or French" gives [{"nl", "fr"}].
    """
    groups = []
    for sentence in _SENTENCE_SPLIT.split(_plain_text(text).lower()):
        mentions = list(_NAME_PATTERN.finditer(sentence))
        if not mentions:
            continue
        sentence_required = _has_cue(sentence, _REQUIRED_CUES)
        clauses, start = [], 0
        for match in _CLAUSE_SPLIT.finditer(sentence):
            clauses.append((start, match.start()))
            start = match.end()
        clauses.append((start, len(sentence)))
        for clause_start, clause_end in clauses:
            clause = sentence[clause_start:clause_end]
            found = [m for m in mentions if clause_start <= m.start() < clause_end]
            if not found or _has_cue(clause, _OPTIONAL_CUES):
                continue
            self_requiring = any(m.group(0).replace(" ", "-").endswith(("speaking", "sprachig", "talig"))
                                 or m.group(1) in _SELF_REQUIRING for m in found)
            if not (sentence_required or self_requiring):
                continue
            group = {_NAME_TO_CODE[found[0].group(1)]}
            for previous, current in zip(found, found[1:], strict=False):
                code = _NAME_TO_CODE[current.group(1)]
                if _ALTERNATIVE.search(clause[previous.end() - clause_start:current.start() - clause_start]):
                    group.add(code)
                else:
                    groups.append(group)
                    group = {code}
            groups.append(group)
    unique = []
    for group in groups:
        if group not in unique:
            unique.append(group)
    return unique


def detect_language(text):
    """The language the text is written in, or None when there is too little text to tell."""
    words = [word.lower() for word in _WORD.findall(_plain_text(text))]
    if len(words) < MIN_DETECTION_WORDS:
        return None
    scores = {code: sum(word in stopwords for word in words) for code, stopwords in _STOPWORDS.items()}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (best, top), (_second, runner_up) = ranked[0], ranked[1]
    if top < 4 or top < runner_up * 1.3 or top < len(words) * MIN_STOPWORD_SHARE:
        return None
    return best


def check_job(title, description, picked):
    """(keep, reason) for a job against the picked language codes. No pick means every language."""
    picked = {str(code).lower() for code in picked or []}
    if not picked:
        return True, ""
    names = ", ".join(LANGUAGES[code]["label"] for code in sorted(picked) if code in LANGUAGES)
    text = f"{title or ''}\n{description or ''}"
    groups = required_languages(text)
    if groups:
        missing = [group for group in groups if not group & picked]
        if not missing:
            return True, ""
        labels = " / ".join(sorted(LANGUAGES[code]["label"] for code in missing[0]))
        return False, f"Requires {labels}, which is not among the picked languages ({names})"
    written_in = detect_language(text)
    if written_in is None or written_in in picked:
        return True, ""
    return False, f"Posted in {LANGUAGES[written_in]['label']}, not in {names}"
