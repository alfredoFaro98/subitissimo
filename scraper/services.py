import time
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from datetime import datetime
from playwright.sync_api import sync_playwright
from .models import SearchQuery # Re-enabled for History
from .text_flags import detect_defects

BASE_SITE = "https://www.subito.it"
HADES_URL = "https://hades.subito.it/v1/search/items"

SEARCH_TEMPLATE = "https://www.subito.it/annunci-italia/vendita/?q={q}"

def safe_get(d: Dict[str, Any], path: str, default=None):
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

def normalize_url(ad: Dict[str, Any]) -> str:
    for p in ("urls.default", "urls.mobile", "urls.desktop", "url"):
        u = safe_get(ad, p)
        if isinstance(u, str) and u.strip():
            return u.strip()
    return ""

def pick_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for k in ("items", "results", "ads", "data"):
        v = payload.get(k)
        if isinstance(v, list):
            return v
    return []

def feature_first(ad: Dict[str, Any], uri: str) -> Dict[str, Any]:
    feats = ad.get("features")
    if not isinstance(feats, list):
        return {}
    for f in feats:
        if isinstance(f, dict) and f.get("uri") == uri:
            vals = f.get("values")
            if isinstance(vals, list) and vals:
                v0 = vals[0]
                return v0 if isinstance(v0, dict) else {}
    return {}

def feature_value(ad: Dict[str, Any], uri: str) -> str:
    v0 = feature_first(ad, uri)
    if not v0:
        return ""
    return str(v0.get("value") or v0.get("key") or "")

def parse_number(value: str) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    m = re.findall(r"[-]?\d[\d\.\,]*", s)
    if not m:
        return None
    num = m[0]

    # formato IT: 1.234,56
    if "." in num and "," in num:
        num = num.replace(".", "").replace(",", ".")
    else:
        if "," in num:
            num = num.replace(",", ".")

    try:
        return float(num)
    except ValueError:
        return None

def first_image_url_browser(ad: Dict[str, Any]) -> str:
    """
    URL immagine apribile direttamente nel browser:
    usa images[0].base_url (dominio s.sbito.it), fallback su cdn_base_url.
    """
    imgs = ad.get("images")
    if not isinstance(imgs, list) or not imgs:
        return ""

    img0 = imgs[0]
    if not isinstance(img0, dict):
        return ""

    url = str(img0.get("base_url") or img0.get("cdn_base_url") or "")
    
    # Fix for hotlinking: usage images.sbito.it API instead of s.sbito.it CDN
    if "s.sbito.it/img/" in url:
        url = url.replace("s.sbito.it/img/", "images.sbito.it/api/v1/sbt-ads-images-pro/images/")
    
    if url and "?" not in url:
        url += "?rule=gallery-desktop-1x-auto"
    return url

def parse_iso_datetime(value: Any) -> Optional[datetime]:
    """Converte la data ISO8601 di Subito in datetime (aware). None se illeggibile."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

# L'API risponde in italiano su questo campo. Vanno tenuti anche i valori
# inglesi: costano nulla e coprono il giorno in cui Subito cambiasse idea.
SPEDIBILE_SI = {"sì", "si", "true", "yes"}


def ad_to_dict(ad: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza un annuncio grezzo dell'API Hades nel dict usato da tutta l'app."""
    id_annuncio = ad.get("urn") or ""
    nome = ad.get("subject") or ad.get("title") or ""
    description = ad.get("body") or ""

    prezzo_str = feature_value(ad, "/price")
    prezzo_num = parse_number(feature_first(ad, "/price").get("key") or prezzo_str)

    data_pub = safe_get(ad, "dates.display", "")
    # Parse ISO date
    data_pub_iso_str = safe_get(ad, "dates.display_iso8601", "")
    # Maintain ISO string for session storage, can parse later
    
    categoria = safe_get(ad, "category.value", "")
    categoria_key = safe_get(ad, "category.key", "")
    regione = safe_get(ad, "geo.region.value", "")
    provincia = safe_get(ad, "geo.city.value", "")
    comune = safe_get(ad, "geo.town.value", "")

    condizione = feature_value(ad, "/item_condition")
    spedizione_tipo = feature_value(ad, "/item_shipping_type")

    costo_sped_str = feature_value(ad, "/item_shipping_cost_tuttosubito")
    costo_sped_num = parse_number(feature_first(ad, "/item_shipping_cost_tuttosubito").get("key") or costo_sped_str)

    # Attenzione: il confronto era con 'true', ma l'API manda "sì"/"no", quindi
    # non era mai vero e il campo usciva sempre False. Il valore finale veniva
    # tutto dal ripiego sul costo qui sotto, e i ~5% di annunci con "Spedizione
    # gestita da te" (spedibili ma senza costo TuttoSubito) risultavano NON
    # spedibili. Misurato su 100 annunci veri: 75 dichiarano sì, ne risultavano 70.
    spedibile_val = feature_value(ad, "/item_shippable").strip().lower()
    spedibile = spedibile_val in SPEDIBILE_SI
    
    # Fallback: if we have a shipping cost, it is shippable
    if costo_sped_num is not None:
        spedibile = True
        
    # Try to find likes/favorites in raw payload 
    likes_val = 0
    if "favorites" in ad:
         try:
             likes_val = int(ad["favorites"])
         except:
             pass
    
    url = normalize_url(ad)
    img_url = first_image_url_browser(ad)
    
    # Defect Detection
    defects = detect_defects(nome, description)
    
    item_dict = {
        'subito_id': id_annuncio,
        'title': nome,
        'price_str': prezzo_str,
        'price_num': prezzo_num,
        'date_pub': data_pub,
        'date_pub_iso': data_pub_iso_str, # Store as string
        'category': categoria,
        'category_key': categoria_key,
        'region': regione,
        'province': provincia,
        'town': comune,
        'condition': condizione,
        'shipping_type': spedizione_tipo,
        'shipping_cost': costo_sped_num,
        'shippable': spedibile,
        'likes_count': likes_val,
        'image_url': img_url,
        'url': url,
        'description': description,
        'defect_flag': defects['flag'],
        'defect_reason': defects['reason']
    }
    return item_dict

def run_search(query: str, limit: int = 35, title_only: bool = False, shippable_only: bool = False, category: str = "", max_pages: int = 200, sleep: float = 0.25) -> List[Dict[str, Any]]:
    q_url = quote_plus(query)
    search_url = SEARCH_TEMPLATE.format(q=q_url)
    if title_only:
        search_url += "&qso=true"
    if shippable_only:
        search_url += "&sh=true"  # Subito parameter for shipping
    
    # Save search history
    total_count = 0 
    search_obj = SearchQuery.objects.create(query=query, limit=limit, title_only=title_only, shippable_only=shippable_only, category=category)
    
    all_ads: List[Dict[str, Any]] = []
    seen = set()
    total_count = 0

    with sync_playwright() as p:
        # Use headless=True for backend service
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="it-IT")
        page = context.new_page()

        try:
            page.goto(BASE_SITE, wait_until="networkidle", timeout=60000)
            time.sleep(1.0)
            page.goto(search_url, wait_until="networkidle", timeout=60000)
            time.sleep(1.5)
            
            # Cookies should be set now
            
            params0 = {"q": query, "start": 0, "lim": limit, "sort": "datedesc"}
            if title_only:
                params0["qso"] = "true"
            if shippable_only:
                params0["sh"] = "true"
            if category:
                params0["c"] = category

            resp0 = context.request.get(HADES_URL, params=params0, timeout=60000)
            
            if resp0.ok:
                first = resp0.json()
                items0 = pick_items(first)
                total_count = int(first.get("count_all") or 0)
                
                # Helper to add ads
                def add_ads_local(items):
                    for ad in items or []:
                        urn = ad.get("urn") or normalize_url(ad)
                        if urn and urn in seen:
                            continue
                        if urn:
                            seen.add(urn)
                        all_ads.append(ad)
                
                add_ads_local(items0)
                
                pages = (total_count + limit - 1) // limit if total_count > 0 else 0
                pages = min(pages, max_pages)
                
                for i in range(1, pages):
                    start = i * limit
                    params = {"q": query, "start": start, "lim": limit, "sort": "datedesc"}
                    if title_only:
                        params["qso"] = "true"
                    if shippable_only:
                        params["sh"] = "true"
                    if category:
                        params["c"] = category
                        
                    try:
                        r = context.request.get(HADES_URL, params=params, timeout=60000)
                    except Exception:
                        continue
                    if not r.ok:
                        continue
                    payload = r.json()
                    add_ads_local(pick_items(payload))
                    time.sleep(sleep)
                    
        finally:
            browser.close()

    # Update total results
    search_obj.total_results = total_count
    search_obj.save()

    items_list = [ad_to_dict(ad) for ad in all_ads]

    return items_list


class HadesError(RuntimeError):
    """Errore di rete/HTTP parlando con l'API di Subito."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class HadesSession:
    """Browser headless tenuto vivo tra una chiamata e l'altra.

    Serve al monitor: l'avvio di Chromium (e il giro sul sito per farsi dare i
    cookie) si paga una volta sola, poi ogni controllo costa una singola
    richiesta JSON. `restart()` rifa' la sessione quando i cookie scadono.
    """

    def __init__(self, headless: bool = True, locale: str = "it-IT"):
        self.headless = headless
        self.locale = locale
        self._pw = None
        self._browser = None
        self._context = None
        self._started_at: Optional[float] = None

    def start(self) -> None:
        self.stop()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(locale=self.locale)
        page = self._context.new_page()
        try:
            page.goto(BASE_SITE, wait_until="networkidle", timeout=60000)
            time.sleep(1.0)
        finally:
            page.close()
        self._started_at = time.monotonic()

    def stop(self) -> None:
        for closer in (self._browser, self._pw):
            if closer is None:
                continue
            try:
                closer.stop() if closer is self._pw else closer.close()
            except Exception:
                pass
        self._pw = None
        self._browser = None
        self._context = None
        self._started_at = None

    def restart(self) -> None:
        self.start()

    @property
    def age_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def fetch_items(self, query: str = "", category: str = "", limit: int = 50, start: int = 0,
                    title_only: bool = False, shippable_only: bool = False,
                    sort: str = "datedesc", timeout: int = 30000):
        """Una pagina di risultati, gia' normalizzata. Ritorna (items, count_all)."""
        if self._context is None:
            self.start()

        params: Dict[str, Any] = {"q": query, "start": start, "lim": limit, "sort": sort}
        if title_only:
            params["qso"] = "true"
        if shippable_only:
            params["sh"] = "true"
        if category:
            params["c"] = category

        try:
            resp = self._context.request.get(HADES_URL, params=params, timeout=timeout)
        except Exception as exc:
            raise HadesError(f"richiesta fallita: {exc}") from exc

        if not resp.ok:
            raise HadesError(f"HTTP {resp.status} dall'API Hades", status=resp.status)

        try:
            payload = resp.json()
        except Exception as exc:
            raise HadesError(f"risposta non JSON: {exc}") from exc

        items = [ad_to_dict(ad) for ad in pick_items(payload)]
        return items, int(payload.get("count_all") or 0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc_info):
        self.stop()
        return False
