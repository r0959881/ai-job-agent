"""Countries and regions a run can search.

Each region knows the place names that identify it in a job's location (used by
the relevance gate) and how each source addresses it (Indeed country, Adzuna
country code, LinkedIn location text). A source that has no entry for a region
is simply not run for it.
"""

REMOTE = "REMOTE"

# id: label, group, flag, indeed country, adzuna code, glassdoor support, markers.
# Markers are lower-case and matched on word boundaries against the job location.
_REGIONS = [
    ("BE", "Belgium", "Europe", "🇧🇪", "belgium", "be", True, [
        "belgium", "belgië", "belgie", "belgique", "belgien", "brussels", "bruxelles", "brussel", "antwerp",
        "antwerpen", "anvers", "ghent", "gent", "gand", "leuven", "louvain", "mechelen", "malines", "liège",
        "liege", "luik", "namur", "namen", "charleroi", "bruges", "brugge", "hasselt", "kortrijk", "aalst",
        "zaventem", "diegem", "wavre", "mons", "flanders", "vlaanderen", "flemish region", "wallonia",
        "wallonie", "walloon region"]),
    ("NL", "Netherlands", "Europe", "🇳🇱", "netherlands", "nl", True, [
        "netherlands", "nederland", "holland", "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague",
        "den haag", "'s-hertogenbosch", "den bosch", "groningen", "tilburg", "breda", "arnhem", "nijmegen",
        "leiden", "delft", "haarlem", "amersfoort", "zwolle", "almere", "noord-holland", "north holland",
        "zuid-holland", "south holland", "noord-brabant", "north brabant"]),
    ("LU", "Luxembourg", "Europe", "🇱🇺", "luxembourg", None, False, [
        "luxembourg", "luxemburg", "esch-sur-alzette", "kirchberg"]),
    ("DE", "Germany", "Europe", "🇩🇪", "germany", "de", True, [
        "germany", "deutschland", "berlin", "munich", "münchen", "muenchen", "hamburg", "frankfurt", "cologne",
        "köln", "koeln", "stuttgart", "düsseldorf", "dusseldorf", "duesseldorf", "leipzig", "dortmund", "essen",
        "bremen", "dresden", "hannover", "hanover", "nuremberg", "nürnberg", "bonn", "karlsruhe", "mannheim",
        "aachen", "bavaria", "bayern"]),
    ("FR", "France", "Europe", "🇫🇷", "france", "fr", True, [
        "france", "paris", "lyon", "marseille", "toulouse", "lille", "bordeaux", "nantes", "nice", "strasbourg",
        "montpellier", "rennes", "grenoble", "île-de-france", "ile-de-france", "la défense", "la defense"]),
    ("GB", "United Kingdom", "Europe", "🇬🇧", "uk", "gb", False, [
        "united kingdom", "uk", "england", "scotland", "wales", "northern ireland", "great britain", "london",
        "manchester", "birmingham", "leeds", "edinburgh", "glasgow", "bristol", "cambridge", "oxford",
        "liverpool", "sheffield", "newcastle", "nottingham", "belfast", "cardiff", "reading"]),
    ("IE", "Ireland", "Europe", "🇮🇪", "ireland", None, True, [
        "ireland", "éire", "dublin", "cork", "galway", "limerick"]),
    ("ES", "Spain", "Europe", "🇪🇸", "spain", "es", True, [
        "spain", "españa", "espana", "madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "málaga",
        "bilbao", "zaragoza"]),
    ("PT", "Portugal", "Europe", "🇵🇹", "portugal", None, False, [
        "portugal", "lisbon", "lisboa", "porto", "braga", "coimbra"]),
    ("IT", "Italy", "Europe", "🇮🇹", "italy", "it", True, [
        "italy", "italia", "milan", "milano", "rome", "roma", "turin", "torino", "bologna", "florence", "firenze",
        "naples", "napoli"]),
    ("CH", "Switzerland", "Europe", "🇨🇭", "switzerland", "ch", True, [
        "switzerland", "schweiz", "suisse", "svizzera", "zurich", "zürich", "geneva", "genève", "geneve", "basel",
        "bern", "lausanne", "zug"]),
    ("AT", "Austria", "Europe", "🇦🇹", "austria", "at", True, [
        "austria", "österreich", "osterreich", "vienna", "wien", "graz", "linz", "salzburg", "innsbruck"]),
    ("DK", "Denmark", "Europe", "🇩🇰", "denmark", None, False, [
        "denmark", "danmark", "copenhagen", "københavn", "kobenhavn", "aarhus", "odense", "aalborg"]),
    ("SE", "Sweden", "Europe", "🇸🇪", "sweden", None, False, [
        "sweden", "sverige", "stockholm", "gothenburg", "göteborg", "goteborg", "malmö", "malmo", "uppsala",
        "linköping", "linkoping"]),
    ("NO", "Norway", "Europe", "🇳🇴", "norway", None, False, [
        "norway", "norge", "oslo", "bergen", "trondheim", "stavanger"]),
    ("FI", "Finland", "Europe", "🇫🇮", "finland", None, False, [
        "finland", "suomi", "helsinki", "espoo", "tampere", "turku", "oulu"]),
    ("PL", "Poland", "Europe", "🇵🇱", "poland", "pl", False, [
        "poland", "polska", "warsaw", "warszawa", "krakow", "kraków", "wroclaw", "wrocław", "gdansk", "gdańsk",
        "poznan", "poznań", "lodz", "łódź"]),
    ("CZ", "Czech Republic", "Europe", "🇨🇿", "czech republic", None, False, [
        "czech republic", "czechia", "česko", "prague", "praha", "brno", "ostrava"]),
    ("RO", "Romania", "Europe", "🇷🇴", "romania", None, False, [
        "romania", "românia", "bucharest", "bucurești", "bucuresti", "cluj-napoca", "cluj", "iasi", "iași",
        "timisoara", "timișoara"]),
    ("GR", "Greece", "Europe", "🇬🇷", "greece", None, False, [
        "greece", "athens", "thessaloniki"]),
    ("HU", "Hungary", "Europe", "🇭🇺", "hungary", None, False, [
        "hungary", "magyarország", "budapest", "debrecen"]),
    ("US", "United States", "Americas", "🇺🇸", "usa", "us", True, [
        "united states", "usa", "u.s.", "new york", "san francisco", "seattle", "boston", "chicago", "austin",
        "los angeles", "washington", "atlanta", "denver", "dallas", "houston", "miami", "california", "texas",
        "new jersey", "massachusetts", "illinois"]),
    ("CA", "Canada", "Americas", "🇨🇦", "canada", "ca", True, [
        "canada", "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "edmonton", "ontario",
        "quebec", "québec", "british columbia", "alberta"]),
    ("MX", "Mexico", "Americas", "🇲🇽", "mexico", "mx", True, [
        "mexico", "méxico", "mexico city", "ciudad de méxico", "guadalajara", "monterrey"]),
    ("BR", "Brazil", "Americas", "🇧🇷", "brazil", "br", True, [
        "brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro", "belo horizonte", "curitiba"]),
    ("AE", "United Arab Emirates", "Middle East & Africa", "🇦🇪", "united arab emirates", None, False, [
        "united arab emirates", "uae", "dubai", "abu dhabi", "sharjah"]),
    ("SA", "Saudi Arabia", "Middle East & Africa", "🇸🇦", "saudi arabia", None, False, [
        "saudi arabia", "ksa", "riyadh", "jeddah", "dammam"]),
    ("QA", "Qatar", "Middle East & Africa", "🇶🇦", "qatar", None, False, ["qatar", "doha"]),
    ("ZA", "South Africa", "Middle East & Africa", "🇿🇦", "south africa", "za", False, [
        "south africa", "johannesburg", "cape town", "pretoria", "durban"]),
    ("IN", "India", "Asia-Pacific", "🇮🇳", "india", "in", True, [
        "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "hyderabad", "pune", "chennai",
        "gurgaon", "gurugram", "noida", "kolkata"]),
    ("PK", "Pakistan", "Asia-Pacific", "🇵🇰", "pakistan", None, False, [
        "pakistan", "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad"]),
    ("SG", "Singapore", "Asia-Pacific", "🇸🇬", "singapore", "sg", True, ["singapore"]),
    ("MY", "Malaysia", "Asia-Pacific", "🇲🇾", "malaysia", None, False, [
        "malaysia", "kuala lumpur", "penang", "johor bahru", "cyberjaya"]),
    ("HK", "Hong Kong", "Asia-Pacific", "🇭🇰", "hong kong", None, True, ["hong kong"]),
    ("JP", "Japan", "Asia-Pacific", "🇯🇵", "japan", None, False, ["japan", "tokyo", "osaka", "yokohama", "kyoto"]),
    ("AU", "Australia", "Asia-Pacific", "🇦🇺", "australia", "au", True, [
        "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra", "new south wales",
        "victoria", "queensland"]),
    ("NZ", "New Zealand", "Asia-Pacific", "🇳🇿", "new zealand", "nz", True, [
        "new zealand", "auckland", "wellington", "christchurch"]),
    (REMOTE, "Remote (worldwide)", "Remote", "🌍", None, None, False, [
        "remote", "anywhere", "worldwide", "work from home", "fully remote", "telecommute"]),
]

REGIONS = {
    rid: {"id": rid, "label": label, "group": group, "flag": flag, "indeed": indeed, "adzuna": adzuna,
          "glassdoor": glassdoor, "markers": markers}
    for rid, label, group, flag, indeed, adzuna, glassdoor, markers in _REGIONS
}
GROUPS = ["Europe", "Americas", "Middle East & Africa", "Asia-Pacific", "Remote"]


def get(region_id):
    return REGIONS.get(str(region_id).upper())


def resolve(region_ids):
    """Known regions in catalog order, ignoring unknown ids and duplicates."""
    wanted = {str(rid).upper() for rid in region_ids or []}
    return [region for rid, region in REGIONS.items() if rid in wanted]


def markers(region_ids):
    return [marker for region in resolve(region_ids) for marker in region["markers"]]


def public_catalog():
    return [{key: region[key] for key in ("id", "label", "group", "flag")} for region in REGIONS.values()]
