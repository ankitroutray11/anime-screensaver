"""
Centralized Anime Franchise Registry for KuroAnime Screensaver.
Defines official franchise allowlists, character rosters, search queries,
tag validators, and negative keyword exclusions to strictly eliminate generic
anime characters and unrelated original artwork.
"""

import copy
import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("KuroFranchiseRegistry")
_CATALOG_LOCK = threading.RLock()
_CATALOG_FILE = Path(__file__).parent / "franchise_catalog.json"

FRANCHISE_REGISTRY: Dict[str, Dict] = {
    "jujutsu-kaisen": {
        "slug": "jujutsu-kaisen",
        "name": "Jujutsu Kaisen",
        "search_queries": ['"Jujutsu Kaisen"', 'Jujutsu Kaisen'],
        "allowlist_tags": {
            "jujutsu kaisen", "sorcery fight", "jjk",
            "satoru gojo", "gojo satoru", "ryomen sukuna", "sukuna",
            "yuji itadori", "itadori yuji", "megumi fushiguro", "fushiguro megumi",
            "nobara kugisaki", "kugisaki nobara", "yuta okkotsu", "okkotsu yuta",
            "maki zenin", "toge inumaki", "kento nanami", "nanami kento",
            "suguru geto", "geto suguru", "toji fushiguro", "fushiguro toji",
            "choso (jujutsu kaisen)", "choso", "mahito", "aoi todo"
        },
        "characters": {
            "Satoru Gojo": ["gojo satoru", "satoru gojo", "gojo"],
            "Ryomen Sukuna": ["ryomen sukuna", "sukuna"],
            "Yuji Itadori": ["yuji itadori", "itadori yuji", "itadori"],
            "Megumi Fushiguro": ["megumi fushiguro", "fushiguro megumi"],
            "Yuta Okkotsu": ["yuta okkotsu", "okkotsu yuta"],
            "Toji Fushiguro": ["toji fushiguro", "fushiguro toji"],
            "Kento Nanami": ["kento nanami", "nanami kento"]
        },
        "negative_keywords": ["-original", "-cosplay", "-vtuber"]
    },
    "demon-slayer": {
        "slug": "demon-slayer",
        "name": "Demon Slayer",
        "search_queries": ['"Kimetsu no Yaiba"', '"Demon Slayer"'],
        "allowlist_tags": {
            "kimetsu no yaiba", "demon slayer", "demon slayer: kimetsu no yaiba",
            "tanjiro kamado", "kamado tanjiro", "nezuko kamado", "kamado nezuko",
            "zenitsu agatsuma", "agatsuma zenitsu", "inosuke hashibira", "hashibira inosuke",
            "giyu tomioka", "tomioka giyu", "shinobu kocho", "kocho shinobu",
            "kyojuro rengoku", "rengoku kyojuro", "tengen uzui", "uzui tengen",
            "muichiro tokito", "tokito muichiro", "mitsuri kanroji", "kanroji mitsuri",
            "obanai iguro", "sanemi shinazugawa", "gyomei himejima",
            "kokushibo", "akaza", "muzan kibutsuji", "kibutsuji muzan", "daki"
        },
        "characters": {
            "Tanjiro Kamado": ["tanjiro kamado", "kamado tanjiro", "tanjiro"],
            "Nezuko Kamado": ["nezuko kamado", "kamado nezuko", "nezuko"],
            "Giyu Tomioka": ["giyu tomioka", "tomioka giyu"],
            "Kyojuro Rengoku": ["kyojuro rengoku", "rengoku kyojuro", "rengoku"],
            "Shinobu Kocho": ["shinobu kocho", "kocho shinobu"],
            "Zenitsu Agatsuma": ["zenitsu agatsuma", "agatsuma zenitsu", "zenitsu"],
            "Kokushibo": ["kokushibo"],
            "Akaza": ["akaza"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "attack-on-titan": {
        "slug": "attack-on-titan",
        "name": "Attack on Titan",
        "search_queries": ['"Shingeki no Kyojin"', '"Attack on Titan"'],
        "allowlist_tags": {
            "shingeki no kyojin", "attack on titan", "snk", "aot",
            "eren yeager", "eren jaeger", "yeager eren", "levi ackerman", "ackerman levi",
            "mikasa ackerman", "ackerman mikasa", "armin arlert", "arlert armin",
            "erwin smith", "smith erwin", "reiner braun", "braun reiner",
            "bertholdt hoover", "annie leonhart", "hange zoe", "zoe hange",
            "historia reiss", "sasha blouse", "colossal titan", "armored titan",
            "attack titan", "beast titan", "founding titan", "survey corps"
        },
        "characters": {
            "Levi Ackerman": ["levi ackerman", "ackerman levi", "levi"],
            "Eren Yeager": ["eren yeager", "eren jaeger", "yeager eren", "eren"],
            "Mikasa Ackerman": ["mikasa ackerman", "ackerman mikasa", "mikasa"],
            "Erwin Smith": ["erwin smith", "smith erwin"],
            "Armin Arlert": ["armin arlert", "arlert armin"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "solo-leveling": {
        "slug": "solo-leveling",
        "name": "Solo Leveling",
        "search_queries": ['"Solo Leveling"', '"Na Honjaman Rebeleob"'],
        "allowlist_tags": {
            "solo leveling", "na honjaman rebeleob", "i alone level up",
            "sung jin-woo", "sung jin woo", "jin-woo sung", "shadow monarch",
            "cha hae-in", "hae-in cha", "beru", "igris", "tusk", "iron",
            "woo jin-chul", "go gun-hee", "thomas andre"
        },
        "characters": {
            "Sung Jin-woo": ["sung jin-woo", "sung jin woo", "jin-woo", "shadow monarch"],
            "Cha Hae-in": ["cha hae-in", "hae-in cha"],
            "Igris": ["igris", "blood-red commander igris"],
            "Beru": ["beru"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "chainsaw-man": {
        "slug": "chainsaw-man",
        "name": "Chainsaw Man",
        "search_queries": ['"Chainsaw Man"'],
        "allowlist_tags": {
            "chainsaw man", "csm", "tatsuki fujimoto",
            "denji", "makima", "power (chainsaw man)", "power", "aki hayakawa", "hayakawa aki",
            "reze", "bomb devil", "chainsaw devil", "pochita", "himeno", "kobeni higashiyama",
            "quanxi", "kishibe", "angel devil", "control devil", "war devil", "asa mitaka"
        },
        "characters": {
            "Denji": ["denji", "chainsaw man"],
            "Makima": ["makima", "control devil"],
            "Power": ["power (chainsaw man)", "power"],
            "Aki Hayakawa": ["aki hayakawa", "hayakawa aki", "aki"],
            "Reze": ["reze", "bomb devil"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "one-piece": {
        "slug": "one-piece",
        "name": "One Piece",
        "search_queries": ['"One Piece"'],
        "allowlist_tags": {
            "one piece", "eiichiro oda", "straw hat pirates",
            "monkey d. luffy", "luffy", "gear 5", "gear fifth", "sun god nika",
            "roronoa zoro", "zoro", "vinsmoke sanji", "sanji", "nami", "nico robin", "robin",
            "tony tony chopper", "usopp", "franky", "brook", "jinbe",
            "portgas d. ace", "ace", "sabo", "shanks", "red hair shanks",
            "trafalgar law", "law", "eustass kid", "edward newgate", "whitebeard",
            "gol d. roger", "donquixote doflamingo", "kaido", "yamato (one piece)", "yamato"
        },
        "characters": {
            "Monkey D. Luffy": ["monkey d. luffy", "luffy", "gear 5", "gear fifth"],
            "Roronoa Zoro": ["roronoa zoro", "zoro"],
            "Vinsmoke Sanji": ["vinsmoke sanji", "sanji"],
            "Portgas D. Ace": ["portgas d. ace", "ace"],
            "Shanks": ["shanks", "red hair shanks"],
            "Trafalgar Law": ["trafalgar law", "law"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "bleach": {
        "slug": "bleach",
        "name": "Bleach",
        "search_queries": ['"Bleach"', '"Thousand-Year Blood War"'],
        "allowlist_tags": {
            "bleach", "tite kubo", "thousand-year blood war", "tybw",
            "ichigo kurosaki", "kurosaki ichigo", "bankai", "rukia kuchiki", "kuchiki rukia",
            "sousuke aizen", "aizen sousuke", "aizen", "kisuke urahara", "urahara kisuke",
            "byakuya kuchiki", "kuchiki byakuya", "toshiro hitsugaya", "hitsugaya toshiro",
            "kenpachi zaraki", "zaraki kenpachi", "ulquiorra cifer", "ulquiorra",
            "grimmjow jaegerjaquez", "grimmjow", "genryusai shigekuni yamamoto",
            "shunsui kyoraku", "yhwach", "jugram haschwalth", "gin ichimaru"
        },
        "characters": {
            "Ichigo Kurosaki": ["ichigo kurosaki", "kurosaki ichigo", "ichigo"],
            "Sosuke Aizen": ["sousuke aizen", "aizen sousuke", "aizen"],
            "Kisuke Urahara": ["kisuke urahara", "urahara kisuke", "urahara"],
            "Byakuya Kuchiki": ["byakuya kuchiki", "kuchiki byakuya"],
            "Kenpachi Zaraki": ["kenpachi zaraki", "zaraki kenpachi", "kenpachi"],
            "Ulquiorra Cifer": ["ulquiorra cifer", "ulquiorra"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "cyberpunk-edgerunners": {
        "slug": "cyberpunk-edgerunners",
        "name": "Cyberpunk: Edgerunners",
        "search_queries": ['"Cyberpunk: Edgerunners"', '"Cyberpunk Edgerunners"'],
        "allowlist_tags": {
            "cyberpunk: edgerunners", "cyberpunk edgerunners", "edgerunners", "studio trigger",
            "david martinez", "martinez david", "lucy (cyberpunk)", "lucyna kushinada",
            "rebecca (cyberpunk)", "maine (cyberpunk)", "dorio (cyberpunk)",
            "kiwi (cyberpunk)", "falco (cyberpunk)", "adam smasher"
        },
        "characters": {
            "Lucy": ["lucy (cyberpunk)", "lucyna kushinada", "lucy"],
            "David Martinez": ["david martinez", "martinez david", "david"],
            "Rebecca": ["rebecca (cyberpunk)", "rebecca"]
        },
        "negative_keywords": ["-original", "-cosplay", "-2077 game"]
    },
    "neon-genesis-evangelion": {
        "slug": "neon-genesis-evangelion",
        "name": "Neon Genesis Evangelion",
        "search_queries": ['"Neon Genesis Evangelion"', '"Evangelion"'],
        "allowlist_tags": {
            "neon genesis evangelion", "evangelion", "nge", "eva", "hideaki anno",
            "shinji ikari", "ikari shinji", "asuka langley soryu", "asuka langley shikinami", "asuka",
            "rei ayanami", "ayanami rei", "rei", "misato katsuragi", "katsuragi misato",
            "kaworu nagisa", "nagisa kaworu", "kaworu", "gendo ikari", "ritsuko akagi",
            "eva unit 01", "eva-01", "eva-02", "nerv", "angel (evangelion)"
        },
        "characters": {
            "Asuka Langley": ["asuka langley soryu", "asuka langley shikinami", "asuka"],
            "Rei Ayanami": ["rei ayanami", "ayanami rei", "rei"],
            "Shinji Ikari": ["shinji ikari", "ikari shinji", "shinji"],
            "Kaworu Nagisa": ["kaworu nagisa", "nagisa kaworu", "kaworu"],
            "Eva Unit 01": ["eva unit 01", "eva-01"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "naruto": {
        "slug": "naruto",
        "name": "Naruto",
        "search_queries": ['"Naruto Shippuden"', '"Naruto"'],
        "allowlist_tags": {
            "naruto", "naruto shippuden", "masashi kishimoto",
            "naruto uzumaki", "uzumaki naruto", "sasuke uchiha", "uchiha sasuke",
            "kakashi hatake", "hatake kakashi", "itachi uchiha", "uchiha itachi",
            "madara uchiha", "uchiha madara", "obito uchiha", "minato namikaze",
            "namikaze minato", "jiraiya", "tsunade", "orochimaru", "hinata hyuga",
            "sakura haruno", "gaara", "pain (naruto)", "nagato", "akatsuki"
        },
        "characters": {
            "Itachi Uchiha": ["itachi uchiha", "uchiha itachi", "itachi"],
            "Kakashi Hatake": ["kakashi hatake", "hatake kakashi", "kakashi"],
            "Naruto Uzumaki": ["naruto uzumaki", "uzumaki naruto", "naruto"],
            "Sasuke Uchiha": ["sasuke uchiha", "uchiha sasuke", "sasuke"],
            "Madara Uchiha": ["madara uchiha", "uchiha madara", "madara"],
            "Minato Namikaze": ["minato namikaze", "namikaze minato", "minato"]
        },
        "negative_keywords": ["-original", "-cosplay", "-boruto"]
    },
    "dragon-ball": {
        "slug": "dragon-ball",
        "name": "Dragon Ball",
        "search_queries": ['"Dragon Ball Z"', '"Dragon Ball Super"', '"Dragon Ball"'],
        "allowlist_tags": {
            "dragon ball", "dragon ball z", "dragon ball super", "dbz", "akira toriyama",
            "son goku", "goku", "ultra instinct", "super saiyan",
            "vegeta", "prince vegeta", "super saiyan blue", "trunks", "future trunks",
            "gohan", "son gohan", "beast gohan", "piccolo", "frieza", "cell",
            "majin buu", "beerus", "whis", "broly", "gogeta", "vegito"
        },
        "characters": {
            "Son Goku": ["son goku", "goku", "ultra instinct"],
            "Vegeta": ["vegeta", "prince vegeta"],
            "Future Trunks": ["future trunks", "trunks"],
            "Gohan": ["gohan", "son gohan", "beast gohan"],
            "Broly": ["broly"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "death-note": {
        "slug": "death-note",
        "name": "Death Note",
        "search_queries": ['"Death Note"'],
        "allowlist_tags": {
            "death note", "tsugumi ohba", "takeshi obata",
            "light yagami", "yagami light", "kira", "l lawliet", "l (death note)",
            "ryuk", "shinigami", "misa amane", "amane misa", "rem (death note)",
            "near (death note)", "mello (death note)"
        },
        "characters": {
            "Light Yagami": ["light yagami", "yagami light", "kira"],
            "L Lawliet": ["l lawliet", "l (death note)", "l"],
            "Ryuk": ["ryuk"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "hunter-x-hunter": {
        "slug": "hunter-x-hunter",
        "name": "Hunter x Hunter",
        "search_queries": ['"Hunter x Hunter"'],
        "allowlist_tags": {
            "hunter x hunter", "hxh", "yoshihiro togashi",
            "killua zoldyck", "zoldyck killua", "killua", "gon freecss", "freecss gon", "gon",
            "kurapika", "leorio paradinight", "hisoka morow", "hisoka", "chrollo lucilfer",
            "lucilfer chrollo", "meruem", "neferpitou", "pitou", "illumi zoldyck", "isaac netero",
            "phantom troupe", "genei ryodan"
        },
        "characters": {
            "Killua Zoldyck": ["killua zoldyck", "zoldyck killua", "killua"],
            "Gon Freecss": ["gon freecss", "freecss gon", "gon"],
            "Hisoka Morow": ["hisoka morow", "hisoka"],
            "Kurapika": ["kurapika"],
            "Chrollo Lucilfer": ["chrollo lucilfer", "lucilfer chrollo", "chrollo"],
            "Meruem": ["meruem"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "frieren": {
        "slug": "frieren",
        "name": "Frieren",
        "search_queries": ['"Sousou no Frieren"', '"Frieren"'],
        "allowlist_tags": {
            "sousou no frieren", "frieren: beyond journey's end", "frieren",
            "fern (frieren)", "fern", "stark (frieren)", "stark",
            "himmel (frieren)", "himmel", "heiter", "eisen (frieren)",
            "flamme (frieren)", "flamme", "serie (frieren)", "serie", "aura the guillotine", "ubel"
        },
        "characters": {
            "Frieren": ["frieren", "sousou no frieren"],
            "Fern": ["fern (frieren)", "fern"],
            "Himmel": ["himmel (frieren)", "himmel"],
            "Stark": ["stark (frieren)", "stark"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "my-hero-academia": {
        "slug": "my-hero-academia",
        "name": "My Hero Academia",
        "search_queries": ['"Boku no Hero Academia"', '"My Hero Academia"'],
        "allowlist_tags": {
            "boku no hero academia", "my hero academia", "mha", "bnha", "kohei horikoshi",
            "izuku midoriya", "midoriya izuku", "deku", "katsuki bakugo", "bakugo katsuki",
            "shoto todoroki", "todoroki shoto", "all might", "toshinori yagi", "endeavor",
            "hawks (boku no hero academia)", "keigo takami", "shota aizawa", "eraserhead",
            "tomura shigaraki", "dabi", "himiko toga", "all for one"
        },
        "characters": {
            "Izuku Midoriya": ["izuku midoriya", "midoriya izuku", "deku"],
            "Katsuki Bakugo": ["katsuki bakugo", "bakugo katsuki", "bakugo"],
            "Shoto Todoroki": ["shoto todoroki", "todoroki shoto", "todoroki"],
            "All Might": ["all might", "toshinori yagi"],
            "Dabi": ["dabi"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "vinland-saga": {
        "slug": "vinland-saga",
        "name": "Vinland Saga",
        "search_queries": ['"Vinland Saga"'],
        "allowlist_tags": {
            "vinland saga", "makoto yukimura",
            "thorfinn", "thorfinn karlsefni", "askeladd", "canute", "king canute",
            "thorkell", "thors", "einar", "gudrid"
        },
        "characters": {
            "Thorfinn": ["thorfinn", "thorfinn karlsefni"],
            "Askeladd": ["askeladd"],
            "Canute": ["canute", "king canute"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "black-clover": {
        "slug": "black-clover",
        "name": "Black Clover",
        "search_queries": ['"Black Clover"'],
        "allowlist_tags": {
            "black clover", "yuki tabata",
            "asta (black clover)", "asta", "yuno grinberryall", "yuno",
            "noelle silva", "silva noelle", "yami sukehiro", "sukehiro yami", "captain yami",
            "julius novachrono", "mereoleona vermillion", "nacht faust", "licht", "zagred"
        },
        "characters": {
            "Asta": ["asta (black clover)", "asta"],
            "Yami Sukehiro": ["yami sukehiro", "sukehiro yami", "yami"],
            "Yuno": ["yuno grinberryall", "yuno"],
            "Noelle Silva": ["noelle silva", "silva noelle"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    },
    "fate-series": {
        "slug": "fate-series",
        "name": "Fate Series",
        "search_queries": ['"Fate/stay night"', '"Fate/Zero"', '"Fate Series"', '"Fate/Grand Order"'],
        "allowlist_tags": {
            "fate (series)", "fate/stay night", "fate/zero", "fate/grand order", "fgo", "type-moon",
            "saber (fate)", "artoria pendragon", "arturia pendragon", "saber alter",
            "archer (fate/stay night)", "emiya", "shirou emiya", "rin tosaka", "tohsaka rin",
            "gilgamesh (fate)", "gilgamesh", "kotomine kirei", "kiritsugu emiya",
            "jeanne d'arc (fate)", "jalter", "mordred (fate)", "astolfo (fate)",
            "mash kyrielight", "ishtar (fate)", "ereshkigal (fate)", "scathach (fate)"
        },
        "characters": {
            "Artoria Pendragon (Saber)": ["saber (fate)", "artoria pendragon", "arturia pendragon"],
            "Archer (EMIYA)": ["archer (fate/stay night)", "emiya"],
            "Gilgamesh": ["gilgamesh (fate)", "gilgamesh"],
            "Rin Tohsaka": ["rin tosaka", "tohsaka rin"],
            "Saber Alter": ["saber alter"]
        },
        "negative_keywords": ["-original", "-cosplay"]
    }
}

GENERIC_DISALLOWED_TAGS: Set[str] = {
    "original", "original character", "oc", "generic", "non-anime",
    "vtuber", "hololive", "nijisanji", "vocaloid", "hatsune miku",
    "genshin impact", "honkai: star rail", "honkai impact",
    "arknights", "azur lane", "blue archive", "touhou"
}

class FranchiseRegistry:
    _DEFAULT_CATALOG_BACKUP: Optional[Dict[str, Dict]] = None

    @classmethod
    def init_catalog(cls, catalog_file: Optional[Path] = None):
        """Loads catalog from JSON file or initializes from defaults."""
        global FRANCHISE_REGISTRY
        target_path = catalog_file or _CATALOG_FILE
        with _CATALOG_LOCK:
            if target_path and target_path.is_file():
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict) and raw:
                        for slug, data in raw.items():
                            allowlist = set(data.get("allowlist_tags", []))
                            entry = dict(data)
                            entry["slug"] = slug
                            entry["allowlist_tags"] = allowlist
                            FRANCHISE_REGISTRY[slug] = entry
                        logger.info("Loaded %d franchises from catalog file %s", len(raw), target_path)
                except Exception as e:
                    logger.warning("Could not load %s, using defaults: %s", target_path, e)

            if cls._DEFAULT_CATALOG_BACKUP is None:
                cls._DEFAULT_CATALOG_BACKUP = copy.deepcopy(FRANCHISE_REGISTRY)

    @staticmethod
    def get_all() -> List[Dict]:
        return list(FRANCHISE_REGISTRY.values())

    @staticmethod
    def get_catalog() -> Dict[str, Dict]:
        """Returns JSON-serializable structured catalog for administration and API."""
        result = {}
        with _CATALOG_LOCK:
            for slug, f in FRANCHISE_REGISTRY.items():
                allowlist = list(f.get("allowlist_tags", []))
                entry = {
                    "slug": slug,
                    "name": f.get("name", slug),
                    "english_aliases": f.get("english_aliases", [f.get("name", slug)]),
                    "japanese_aliases": f.get("japanese_aliases", []),
                    "search_queries": f.get("search_queries", [f.get("name", slug)]),
                    "wallhaven_tag_ids": f.get("wallhaven_tag_ids", []),
                    "character_tag_ids": f.get("character_tag_ids", {}),
                    "allowlist_tags": sorted(allowlist) if isinstance(allowlist, list) else sorted(list(allowlist)),
                    "characters": f.get("characters", {}),
                    "negative_keywords": f.get("negative_keywords", ["-original", "-cosplay"]),
                    "excluded_tag_ids": f.get("excluded_tag_ids", []),
                    "excluded_keywords": f.get("excluded_keywords", [])
                }
                result[slug] = entry
        return result

    @classmethod
    def update_franchise_catalog_entry(
        cls,
        slug: str,
        data: Dict[str, Any],
        save_file: bool = True
    ) -> Dict[str, Any]:
        """
        Dynamically updates a franchise catalog entry at runtime and persists to JSON.
        Validates structure to ensure non-empty display name and valid tag lists.
        """
        slug = slug.strip().lower()
        if not slug:
            raise ValueError("Franchise slug cannot be empty.")

        with _CATALOG_LOCK:
            current = FRANCHISE_REGISTRY.get(slug, {})
            name = data.get("name") or current.get("name") or slug.replace("-", " ").title()

            wallhaven_tag_ids = [int(tid) for tid in data.get("wallhaven_tag_ids", current.get("wallhaven_tag_ids", []))]
            excluded_tag_ids = [int(tid) for tid in data.get("excluded_tag_ids", current.get("excluded_tag_ids", []))]

            raw_allowlist = data.get("allowlist_tags", current.get("allowlist_tags", []))
            allowlist_set = set(t.lower().strip() for t in raw_allowlist if str(t).strip())

            updated_entry = {
                "slug": slug,
                "name": name,
                "english_aliases": data.get("english_aliases", current.get("english_aliases", [name])),
                "japanese_aliases": data.get("japanese_aliases", current.get("japanese_aliases", [])),
                "search_queries": data.get("search_queries", current.get("search_queries", [name])),
                "wallhaven_tag_ids": wallhaven_tag_ids,
                "character_tag_ids": data.get("character_tag_ids", current.get("character_tag_ids", {})),
                "allowlist_tags": allowlist_set,
                "characters": data.get("characters", current.get("characters", {})),
                "negative_keywords": data.get("negative_keywords", current.get("negative_keywords", ["-original", "-cosplay"])),
                "excluded_tag_ids": excluded_tag_ids,
                "excluded_keywords": data.get("excluded_keywords", current.get("excluded_keywords", []))
            }

            FRANCHISE_REGISTRY[slug] = updated_entry

            if save_file:
                cls.save_catalog()

            # Return JSON-friendly copy
            res = dict(updated_entry)
            res["allowlist_tags"] = sorted(list(allowlist_set))
            return res

    @classmethod
    def save_catalog(cls, catalog_file: Optional[Path] = None):
        """Persists current in-memory catalog to JSON file."""
        target_path = catalog_file or _CATALOG_FILE
        data = cls.get_catalog()
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Persisted franchise catalog (%d franchises) to %s", len(data), target_path)

    @classmethod
    def reset_catalog_to_defaults(cls, save_file: bool = True) -> Dict[str, Dict]:
        """Resets the catalog to factory default state."""
        global FRANCHISE_REGISTRY
        with _CATALOG_LOCK:
            if cls._DEFAULT_CATALOG_BACKUP:
                FRANCHISE_REGISTRY = copy.deepcopy(cls._DEFAULT_CATALOG_BACKUP)
            elif _CATALOG_FILE.is_file():
                with open(_CATALOG_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for slug, data in raw.items():
                    entry = dict(data)
                    entry["slug"] = slug
                    entry["allowlist_tags"] = set(data.get("allowlist_tags", []))
                    FRANCHISE_REGISTRY[slug] = entry
            if save_file and _CATALOG_FILE.is_file():
                cls.save_catalog()
            return cls.get_catalog()

    @staticmethod
    def verify_tag_id_online(tag_id: int, timeout: float = 6.0) -> Dict[str, Any]:
        """
        Directly queries Wallhaven API (https://wallhaven.cc/api/v1/tag/{id}) to verify
        the numeric tag ID, discover category, and confirm exact name.
        Never invents IDs.
        """
        url = f"https://wallhaven.cc/api/v1/tag/{int(tag_id)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            tag_data = data.get("data", {})
            return {
                "id": tag_data.get("id"),
                "name": tag_data.get("name"),
                "category": tag_data.get("category"),
                "purity": tag_data.get("purity"),
                "created_at": tag_data.get("created_at"),
                "is_valid": True,
                "error": None
            }
        except urllib.error.HTTPError as he:
            return {
                "id": tag_id,
                "is_valid": False,
                "error": f"HTTP {he.code}: {he.reason}"
            }
        except Exception as ex:
            return {
                "id": tag_id,
                "is_valid": False,
                "error": str(ex)
            }

    @staticmethod
    def get_franchise(identifier: str) -> Optional[Dict]:
        if not identifier:
            return None
        clean = identifier.lower().strip()
        # Match by slug
        if clean in FRANCHISE_REGISTRY:
            return FRANCHISE_REGISTRY[clean]
        # Match by display name
        for f in FRANCHISE_REGISTRY.values():
            if f["name"].lower() == clean:
                return f
        # Match by english or japanese aliases
        for f in FRANCHISE_REGISTRY.values():
            for alias in f.get("english_aliases", []) + f.get("japanese_aliases", []):
                if alias.lower() == clean:
                    return f
        # Match by partial tag
        for f in FRANCHISE_REGISTRY.values():
            if clean in f["allowlist_tags"]:
                return f
        return None

    @staticmethod
    def validate_tags(
        franchise_slug: str,
        tags: List[str],
        tag_ids: Optional[List[int]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates tags against franchise allowlist and strictly protects against ambiguous keywords.
        Returns (is_valid: bool, identified_character: Optional[str]).
        Rejects generic, unrelated, or ambiguous artwork.
        """
        f = FRANCHISE_REGISTRY.get(franchise_slug)
        if not f:
            return False, None

        normalized_tags = [str(t).lower().strip() for t in tags]

        # 1. Reject if any generic/disallowed tag is present
        for t in normalized_tags:
            if t in GENERIC_DISALLOWED_TAGS:
                return False, None

        # 2. Reject if any excluded tag ID is present (e.g. tag 243 for One Piece)
        if tag_ids:
            excluded_ids = set(f.get("excluded_tag_ids", []))
            for tid in tag_ids:
                if tid in excluded_ids:
                    return False, None

        # 3. Reject if any ambiguity keyword appears in tags
        excluded_keywords = [k.lower().strip() for k in f.get("excluded_keywords", []) if k.strip()]
        for t in normalized_tags:
            for ek in excluded_keywords:
                if ek in t:
                    return False, None

        # 4. Check if at least one franchise allowlist tag matches
        has_franchise_tag = any(t in f["allowlist_tags"] for t in normalized_tags)
        if not has_franchise_tag:
            return False, None

        # 5. Detect character
        identified_char = None
        for char_name, aliases in f.get("characters", {}).items():
            for alias in aliases:
                if any(alias in t for t in normalized_tags):
                    identified_char = char_name
                    break
            if identified_char:
                break

        return True, identified_char

    @staticmethod
    def build_wallhaven_tag_query(
        tag_id: int,
        negative_keywords: Optional[List[str]] = None,
        page: int = 1,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080"
    ) -> str:
        """
        Constructs Strategy A query: numeric tag search 'id:<tag_id>' with exclusions.
        """
        terms = [f"id:{int(tag_id)}"]
        if negative_keywords:
            for neg in negative_keywords:
                neg_str = neg if neg.startswith("-") else f"-{neg}"
                if neg_str not in terms:
                    terms.append(neg_str)

        full_q = " ".join(terms)
        encoded_q = urllib.parse.quote(full_q)

        ratio_param = ""
        if ratio == "landscape":
            ratio_param = "&ratios=16x9,16x10"
        elif ratio in ["dual", "32:9", "32x9", "dual_screen"]:
            ratio_param = "&ratios=32x9,32x10,21x9"
        elif ratio == "ultrawide":
            ratio_param = "&ratios=21x9,32x9,16x9"
        elif ratio == "portrait":
            ratio_param = "&ratios=9x16,10x16"
        elif ratio in ["16x9", "16x10", "21x9", "32x9", "9x16", "10x16"]:
            ratio_param = f"&ratios={ratio}"

        return f"https://wallhaven.cc/api/v1/search?q={encoded_q}&categories=010&purity=100&atleast={min_resolution}&sorting=favorites&page={page}{ratio_param}"

    @staticmethod
    def build_wallhaven_keyword_query(
        keyword: str,
        negative_keywords: Optional[List[str]] = None,
        page: int = 1,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080"
    ) -> str:
        """
        Constructs Strategy B query: keyword/phrase search with exclusions.
        """
        clean_kw = keyword.strip()
        if not (clean_kw.startswith('"') and clean_kw.endswith('"')):
            clean_kw = f'"{clean_kw}"'

        terms = [clean_kw]
        if negative_keywords:
            for neg in negative_keywords:
                neg_str = neg if neg.startswith("-") else f"-{neg}"
                if neg_str not in terms:
                    terms.append(neg_str)

        full_q = " ".join(terms)
        encoded_q = urllib.parse.quote(full_q)

        ratio_param = ""
        if ratio == "landscape":
            ratio_param = "&ratios=16x9,16x10"
        elif ratio in ["dual", "32:9", "32x9", "dual_screen"]:
            ratio_param = "&ratios=32x9,32x10,21x9"
        elif ratio == "ultrawide":
            ratio_param = "&ratios=21x9,32x9,16x9"
        elif ratio == "portrait":
            ratio_param = "&ratios=9x16,10x16"
        elif ratio in ["16x9", "16x10", "21x9", "32x9", "9x16", "10x16"]:
            ratio_param = f"&ratios={ratio}"

        return f"https://wallhaven.cc/api/v1/search?q={encoded_q}&categories=010&purity=100&atleast={min_resolution}&sorting=favorites&page={page}{ratio_param}"

    @staticmethod
    def build_wallhaven_query(
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        excluded_franchises: Optional[List[str]] = None,
        excluded_characters: Optional[List[str]] = None,
        page: int = 1,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080"
    ) -> str:
        """
        Constructs a safe-only, franchise-specific Wallhaven search query string.
        """
        f = FRANCHISE_REGISTRY.get(franchise_slug) if franchise_slug else None

        query_terms = []
        if character_name:
            query_terms.append(f'"{character_name}"')
        elif f and f.get("wallhaven_tag_ids"):
            # Default to primary verified tag ID if available
            query_terms.append(f"id:{f['wallhaven_tag_ids'][0]}")
        elif f and f.get("search_queries"):
            query_terms.append(f["search_queries"][0])
        else:
            query_terms.append('"Anime"')

        # Add negative exclusions
        negatives = ["-original", "-cosplay"]
        if f:
            for neg in f.get("negative_keywords", []):
                if neg not in negatives:
                    negatives.append(neg)

        # Exclude specified franchises
        if excluded_franchises:
            for ex in excluded_franchises:
                ex_f = FranchiseRegistry.get_franchise(ex)
                if ex_f and ex_f.get("slug") != franchise_slug:
                    negatives.append(f'-"{ex_f["name"]}"')

        # Exclude specified characters
        if excluded_characters:
            for ec in excluded_characters:
                negatives.append(f'-"{ec}"')

        full_q = " ".join(query_terms + negatives)
        encoded_q = urllib.parse.quote(full_q)

        ratio_param = ""
        if ratio == "landscape":
            ratio_param = "&ratios=16x9,16x10"
        elif ratio in ["dual", "32:9", "32x9", "dual_screen"]:
            ratio_param = "&ratios=32x9,32x10,21x9"
        elif ratio == "ultrawide":
            ratio_param = "&ratios=21x9,32x9,16x9"
        elif ratio == "portrait":
            ratio_param = "&ratios=9x16,10x16"
        elif ratio in ["16x9", "16x10", "21x9", "32x9", "9x16", "10x16"]:
            ratio_param = f"&ratios={ratio}"

        return f"https://wallhaven.cc/api/v1/search?q={encoded_q}&categories=010&purity=100&atleast={min_resolution}&sorting=favorites&page={page}{ratio_param}"


# Initialize catalog from franchise_catalog.json if present
FranchiseRegistry.init_catalog()

