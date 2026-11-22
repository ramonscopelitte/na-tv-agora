#!/usr/bin/env python3
"""Gera data/agenda.json: os melhores eventos do dia e onde passam na TV brasileira.

1. Pega os jogos do dia na ESPN (futebol, NBA, NFL, NHL).
2. Dá uma nota "vale a pena" a cada um.
3. Procura o canal no guia meuguia.tv (canais confirmados).
   Se não achar, usa a tabela de direitos (canal provável).
   Se não tiver canal nenhum, o evento fica de fora.
4. Acrescenta os extras: tudo que o guia marca "Ao Vivo" em esporte e não veio
   da ESPN (F1, MotoGP, tênis, futsal, vôlei, UFC...).

Só usa a biblioteca padrão do Python (3.9+).
"""
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LISBOA = ZoneInfo("Europe/Lisbon")
BRASILIA = ZoneInfo("America/Sao_Paulo")
NOVA_YORK = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
SAIDA = Path(__file__).resolve().parent.parent / "data" / "agenda.json"

# ---------------------------------------------------------------- ligas da ESPN
# slug: (nome em português, grupo, peso da competição, duração em minutos)
LIGAS = {
    "soccer/fifa.world": ("Copa do Mundo", "futebol", 5.0, 115),
    "soccer/uefa.champions": ("Champions League", "futebol", 4.5, 115),
    "soccer/conmebol.libertadores": ("Libertadores", "futebol", 4.0, 115),
    "soccer/bra.copa_do_brazil": ("Copa do Brasil", "futebol", 3.6, 115),
    "soccer/bra.1": ("Brasileirão", "futebol", 4.0, 115),
    "soccer/eng.1": ("Premier League", "futebol", 3.5, 115),
    "soccer/esp.1": ("La Liga", "futebol", 3.2, 115),
    "soccer/ita.1": ("Serie A Italiana", "futebol", 3.0, 115),
    "soccer/uefa.europa": ("Liga Europa", "futebol", 3.0, 115),
    "soccer/conmebol.sudamericana": ("Sul-Americana", "futebol", 3.0, 115),
    "soccer/ger.1": ("Bundesliga", "futebol", 2.8, 115),
    "soccer/fra.1": ("Ligue 1", "futebol", 2.5, 115),
    "soccer/por.1": ("Liga Portugal", "futebol", 2.4, 115),
    "soccer/arg.1": ("Campeonato Argentino", "futebol", 2.3, 115),
    "soccer/uefa.europa.conf": ("Conference League", "futebol", 2.2, 115),
    "soccer/bra.2": ("Brasileirão Série B", "futebol", 2.0, 115),
    "soccer/usa.1": ("MLS", "futebol", 2.0, 115),
    "soccer/ned.1": ("Campeonato Holandês", "futebol", 2.0, 115),
    "soccer/eng.fa": ("Copa da Inglaterra", "futebol", 2.5, 115),
    "soccer/esp.copa_del_rey": ("Copa do Rei", "futebol", 2.5, 115),
    "soccer/ita.coppa_italia": ("Copa da Itália", "futebol", 2.3, 115),
    "soccer/fifa.friendly": ("Amistoso", "futebol", 2.0, 115),
    "soccer/fifa.worldq.conmebol": ("Eliminatórias", "futebol", 4.0, 115),
    "soccer/eng.2": ("Inglês 2ª divisão", "futebol", 1.5, 115),
    "soccer/tur.1": ("Campeonato Turco", "futebol", 1.5, 115),
    "soccer/ger.2": ("Bundesliga 2ª divisão", "futebol", 1.3, 115),
    "soccer/rus.1": ("Campeonato Russo", "futebol", 1.3, 115),
    "soccer/ksa.1": ("Campeonato Saudita", "futebol", 1.5, 115),
    "basketball/nba": ("NBA", "basquete", 3.0, 150),
    "football/nfl": ("NFL", "nfl", 3.0, 200),
    "hockey/nhl": ("NHL", "outros", 1.5, 160),
}

# Tabela de direitos: canal PROVÁVEL quando o jogo não aparece no guia.
# Só entra o que sabemos com alguma segurança. Edite à vontade.
DIREITOS = {
    "soccer/esp.1": [["CazéTV", "yt"]],
    "soccer/fra.1": [["CazéTV", "yt"]],
    "soccer/ita.1": [["CazéTV", "yt"], ["Disney+", "web"]],
    "soccer/ger.1": [["Canal GOAT", "yt"], ["XSports", "tv"]],
    "soccer/ger.2": [["Canal GOAT", "yt"]],
    "soccer/usa.1": [["Apple TV", "web"]],
    "soccer/bra.1": [["Premiere", "tv"]],
    "basketball/nba": [["Prime Video", "web"], ["NBA League Pass", "web"]],
    "football/nfl": [["NFL Game Pass", "web"]],
}

# Canais do meuguia.tv: código -> nome
CANAIS = {
    "ESP": "ESPN", "ES2": "ESPN 2", "ES3": "ESPN 3", "ES4": "ESPN 4", "ES5": "ESPN 5",
    "SPO": "SporTV", "SP2": "SporTV 2", "SP3": "SporTV 3",
    "BSP": "BandSports", "121": "Premiere", "135": "Combate",
    "GRD": "Globo", "REC": "Record", "BAN": "Band", "SBT": "SBT", "RTV": "RedeTV!",
    "CUL": "TV Cultura", "TED": "TV Brasil",
}

GRANDES = {
    # futebol
    "real madrid", "barcelona", "manchester city", "liverpool", "arsenal", "manchester united", "chelsea",
    "tottenham", "paris saint germain", "bayern munich", "borussia dortmund", "internazionale", "ac milan",
    "juventus", "napoli", "atletico madrid", "benfica", "porto", "sporting cp", "boca juniors", "river plate",
    "flamengo", "palmeiras", "corinthians", "sao paulo", "santos", "vasco da gama", "fluminense", "botafogo",
    "gremio", "internacional", "atletico mineiro", "cruzeiro", "bahia",
    # NBA
    "los angeles lakers", "boston celtics", "golden state warriors", "new york knicks", "oklahoma city thunder",
    "denver nuggets", "milwaukee bucks", "dallas mavericks", "philadelphia 76ers",
    # NFL
    "kansas city chiefs", "philadelphia eagles", "dallas cowboys", "san francisco 49ers", "buffalo bills",
    "detroit lions", "baltimore ravens", "green bay packers",
}
BRASILEIROS_INTL = {"soccer/conmebol.libertadores", "soccer/conmebol.sudamericana", "soccer/fifa.friendly",
                    "soccer/fifa.world", "soccer/fifa.worldq.conmebol"}

NOMES_PT = {
    "Internazionale": "Inter de Milão", "Bayern Munich": "Bayern de Munique", "Atlético Madrid": "Atlético de Madrid",
    "Hamburg SV": "Hamburgo", "Brighton & Hove Albion": "Brighton", "Paris Saint-Germain": "PSG",
    "Athletico Paranaense": "Athletico-PR", "Atlético Mineiro": "Atlético-MG", "Atlético Goianiense": "Atlético-GO",
    "Vasco da Gama": "Vasco", "Brazil": "Brasil", "Argentina": "Argentina", "Germany": "Alemanha", "Spain": "Espanha",
    "France": "França", "England": "Inglaterra", "Italy": "Itália", "Portugal": "Portugal", "Netherlands": "Holanda",
    "Stade Rennais": "Rennes", "AC Milan": "Milan", "Ajax Amsterdam": "Ajax", "Dinamo Moscow": "Dynamo Moscou",
    "Spartak Moscow": "Spartak Moscou", "Red Bull Bragantino": "Bragantino", "Sporting CP": "Sporting",
}

# Palavras que não servem para casar nomes de times
GENERICAS = {"fc", "cf", "sc", "ac", "afc", "club", "clube", "de", "da", "do", "del", "the", "city", "united",
             "real", "sporting", "athletic", "atletico", "state", "new", "york", "los", "angeles", "san", "saint",
             "st", "dynamo", "dinamo", "olympique", "ao", "vivo", "x", "vs", "red", "bull", "sao", "santa", "inter",
             "nba", "nfl", "nhl", "jogo", "final", "semifinal", "rovers", "town", "sv", "cd", "ud", "rc"}

ALIAS = {  # nome que aparece no guia -> palavra que a ESPN usa
    "inter de milao": "internazionale", "bayern de munique": "bayern", "hamburgo": "hamburg",
    "atletico de madrid": "madrid", "dinamo de moscou": "moscow", "spartak moscou": "spartak",
    "galo": "mineiro", "furacao": "paranaense", "athletico pr": "paranaense", "atletico mg": "mineiro",
    "atletico go": "goianiense", "bragantino": "bragantino", "psg": "paris",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s)


def palavras(s):
    t = norm(s)
    for k, v in ALIAS.items():
        t = t.replace(k, v)
    return {w for w in t.split() if len(w) >= 3 and w not in GENERICAS}


def baixar(url, tentativas=3):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                print(f"  falhou: {url} ({e})", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


# ------------------------------------------------------------------- ESPN
def eventos_espn(datas):
    tarefas = [(lg, d) for lg in LIGAS for d in datas]

    def um(par):
        lg, d = par
        txt = baixar(f"https://site.api.espn.com/apis/site/v2/sports/{lg}/scoreboard?dates={d}&limit=200")
        return lg, d, json.loads(txt) if txt else None

    vistos, saida = set(), []
    with ThreadPoolExecutor(8) as ex:
        for lg, d, js in ex.map(um, tarefas):
            if not js:
                continue
            for e in js.get("events", []):
                if e["id"] in vistos:
                    continue
                vistos.add(e["id"])
                c = e["competitions"][0]
                casa = next((t for t in c["competitors"] if t.get("homeAway") == "home"), c["competitors"][0])
                fora = next((t for t in c["competitors"] if t is not casa), c["competitors"][-1])
                notas = [n.get("headline", "") for n in c.get("notes", []) if n.get("headline")]
                ini = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
                saida.append({
                    "lg": lg, "id": e["id"], "ini": ini,
                    "casa": casa["team"]["displayName"], "fora": fora["team"]["displayName"],
                    "casa_curto": casa["team"].get("shortDisplayName", ""), "fora_curto": fora["team"].get("shortDisplayName", ""),
                    "nota_fase": notas[0] if notas else "",
                    "d": ini.astimezone(NOVA_YORK).strftime("%Y%m%d"),
                })
    return saida


def nota(ev):
    nome, grupo, peso, _ = LIGAS[ev["lg"]]
    sc = peso
    times = {norm(ev["casa"]).strip(), norm(ev["fora"]).strip()}
    grandes = sum(1 for t in times if re.sub(r"\s+", " ", t) in GRANDES)
    sc += min(1.5, grandes * 1.0)
    fase = norm(ev["nota_fase"])
    if re.search(r"\bfinal\b", fase) and "semi" not in fase and "quarter" not in fase:
        sc += 2
    elif "semi" in fase:
        sc += 1.5
    elif re.search(r"quarter|round of 16|playoff|knockout|leg", fase):
        sc += 0.8
    if ev["lg"] in BRASILEIROS_INTL and any("brazil" in t for t in times):
        sc += 1.5
    return round(sc, 2)


def estrelas(sc):
    return 3 if sc >= 5 else 2 if sc >= 4 else 1


def nome_pt(n):
    return NOMES_PT.get(n, n)


# ------------------------------------------------------------------- guia
def programacao(codigo):
    txt = baixar(f"https://meuguia.tv/programacao/canal/{codigo}")
    if not txt:
        return []
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    hoje = datetime.now(BRASILIA)
    itens, dia = [], None
    padrao = re.compile(
        r'subheader devicepadding">\s*([^<]+?)\s*</li>'
        r"|class='lileft time'>(\d\d:\d\d)</div>\s*<div class=\"licontent\">\s*<h2>(.*?)</h2>\s*<h3>(.*?)</h3>",
        re.S)
    for m in padrao.finditer(txt):
        if m.group(1):
            dm = re.search(r"(\d\d)/(\d\d)", m.group(1))
            if dm:
                d, mes = int(dm.group(1)), int(dm.group(2))
                ano = hoje.year + (1 if mes < hoje.month - 6 else -1 if mes > hoje.month + 6 else 0)
                dia = (ano, mes, d)
            continue
        if not dia:
            continue
        hh, mm = map(int, m.group(2).split(":"))
        ini = datetime(dia[0], dia[1], dia[2], hh, mm, tzinfo=BRASILIA)
        if itens and ini < itens[-1]["ini"]:  # virou o dia sem cabeçalho
            ini += timedelta(days=1)
            dia = (ini.year, ini.month, ini.day)
        itens.append({"ini": ini, "titulo": html.unescape(m.group(3)).strip(),
                      "cat": html.unescape(m.group(4)).strip()})
    for a, b in zip(itens, itens[1:]):
        a["fim"] = b["ini"]
    if itens:
        itens[-1]["fim"] = itens[-1]["ini"] + timedelta(hours=2)
    # junta blocos seguidos do mesmo programa (o guia divide o NFL RedZone por hora, por exemplo)
    juntos = []
    for it in itens:
        if juntos and norm(limpar_titulo(juntos[-1]["titulo"])) == norm(limpar_titulo(it["titulo"])) \
                and juntos[-1]["fim"] == it["ini"]:
            juntos[-1]["fim"] = it["fim"]
            continue
        juntos.append(it)
    return juntos


def guia_completo():
    with ThreadPoolExecutor(6) as ex:
        res = dict(zip(CANAIS, ex.map(programacao, CANAIS)))
    saida = []
    for cod, itens in res.items():
        for it in itens:
            ao_vivo = "ao vivo" in norm(it["titulo"])
            esporte = norm(it["cat"]).startswith("esporte")
            if ao_vivo and esporte:
                it["canal"] = CANAIS[cod]
                saida.append(it)
        print(f"  guia {CANAIS[cod]}: {len(itens)} programas", file=sys.stderr)
    return saida


def limpar_titulo(t):
    t = re.sub(r"\s*-\s*Ao Vivo\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def casar(ev, guia):
    """Programas do guia que são este jogo: horário perto e nome dos dois times."""
    pc, pf = palavras(ev["casa"] + " " + ev["casa_curto"]), palavras(ev["fora"] + " " + ev["fora_curto"])
    achados = []
    for g in guia:
        delta = (g["ini"] - ev["ini"]).total_seconds() / 60
        if not -45 <= delta <= 75:
            continue
        pg = palavras(g["titulo"])
        if (pc & pg) and (pf & pg):
            achados.append(g)
    return achados


GRUPO_EXTRA = [
    (r"futsal|futebol|copa|campeonato|liga|x ", "futebol"),
    (r"formula|f1|motogp|moto2|moto3|stock car|porsche|nascar|indy|rali|wec|automobilismo|motociclismo", "motor"),
    (r"tenis|atp|wta|roland|wimbledon|us open|australian open", "tenis"),
    (r"nba|nbb|basquete", "basquete"),
    (r"nfl|futebol americano", "nfl"),
]


def grupo_extra(titulo, cat):
    t = norm(titulo + " " + cat)
    if "futsal" in t:
        return "futebol"
    for rx, g in GRUPO_EXTRA[1:]:
        if re.search(rx, t):
            return g
    if re.search(r"futebol", norm(cat)):
        return "futebol"
    return "outros"


def nota_extra(titulo, cat):
    t = norm(titulo)
    sc = 2.0
    if re.search(r"formula 1|\bf1\b", t) and not re.search(r"treino|classific|sprint", t):
        sc = 5.0
    elif re.search(r"formula 1|\bf1\b|motogp", t):
        sc = 3.5
    elif re.search(r"\bufc\b", t):
        sc = 3.5
    elif re.search(r"\batp\b|\bwta\b|tenis", t):
        sc = 2.5
    if re.search(r"\bfinal\b", t) and "semi" not in t:
        sc += 2.5
    elif "semi" in t:
        sc += 1
    if "duplas" in t:
        sc -= 1
    if re.search(r"\bbrasil\s+x\b|\bx\s+brasil\b", t):  # seleção brasileira
        sc += 2.5
    return round(sc, 2)


COMP_PT = {"futebol de salao": "Futsal", "sail gp": "SailGP", "luta": "Lutas"}


def comp_extra(titulo, cat):
    partes = [p.strip() for p in re.split(r":| - ", titulo) if p.strip()]
    if len(partes) > 1 and len(partes[0]) < 40:
        comp, resto = partes[0], " - ".join(partes[1:])
    else:
        comp, resto = (cat.split("/")[-1] if "/" in cat else cat), titulo
    return COMP_PT.get(norm(comp).strip(), comp), resto


def parecidos(a, b):
    pa, pb = palavras(a), palavras(b)
    return bool(pa and pb) and len(pa & pb) / len(pa | pb) >= 0.5


# ------------------------------------------------------------------- montagem
def main():
    agora = datetime.now(LISBOA)
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=2)
    datas_et = sorted({(inicio + timedelta(hours=h)).astimezone(NOVA_YORK).strftime("%Y%m%d") for h in range(0, 49, 6)})

    print("ESPN...", file=sys.stderr)
    espn = [e for e in eventos_espn(datas_et) if inicio <= e["ini"].astimezone(LISBOA) < fim]
    print(f"  {len(espn)} jogos na janela", file=sys.stderr)
    print("Guia...", file=sys.stderr)
    guia = [g for g in guia_completo() if inicio - timedelta(hours=1) <= g["ini"] < fim]
    print(f"  {len(guia)} transmissões ao vivo de esporte", file=sys.stderr)

    usados = set()
    eventos = []
    sem_canal = 0
    for ev in espn:
        nome, grupo, _, dur = LIGAS[ev["lg"]]
        achados = casar(ev, guia)
        canais = []
        for g in achados:
            usados.add(id(g))
            if g["canal"] not in [c[0] for c in canais]:
                canais.append([g["canal"], "tv", "c"])
        if not canais and ev["lg"] in DIREITOS:
            canais = [c + ["p"] for c in DIREITOS[ev["lg"]]]
        if not canais:
            sem_canal += 1
            continue
        sc = nota(ev)
        esporte = ev["lg"].split("/")[1] if not ev["lg"].startswith("soccer") else "futebol"
        caminho = {"nba": "nba/jogo", "nfl": "nfl/jogo", "nhl": "nhl/jogo"}.get(esporte, "futebol/partida")
        eventos.append({
            "id": "espn-" + ev["id"],
            "ini": ev["ini"].isoformat().replace("+00:00", "Z"),
            "fim": (ev["ini"] + timedelta(minutes=dur)).isoformat().replace("+00:00", "Z"),
            "g": grupo, "c": nome,
            "t": f"{nome_pt(ev['casa'])} x {nome_pt(ev['fora'])}",
            "n": traduz_fase(ev["nota_fase"]),
            "ch": canais, "s": estrelas(sc), "sc": sc,
            "x": f"https://www.espn.com.br/{caminho}/_/jogoId/{ev['id']}",
            "e": {"lg": ev["lg"], "id": ev["id"], "d": ev["d"]},
        })

    # extras: o que o guia tem ao vivo e não casou com a ESPN
    extras = {}
    for g in guia:
        if id(g) in usados:
            continue
        titulo = limpar_titulo(g["titulo"])
        if re.search(r"^vt\b|reprise|melhores momentos|pre jogo|pré-jogo|pos jogo|pós-jogo|resenha", norm(titulo)):
            continue
        chave = (g["ini"].astimezone(timezone.utc).strftime("%Y%m%d%H%M"), norm(titulo))
        igual = next((k for k, x in extras.items()
                      if abs((x["_ini"] - g["ini"]).total_seconds()) <= 90 * 60 and parecidos(x["_tit"], titulo)), None)
        if igual:
            x = extras[igual]
            if g["canal"] not in [c[0] for c in x["ch"]]:
                x["ch"].append([g["canal"], "tv", "c"])
            continue
        comp, t = comp_extra(titulo, g["cat"])
        sc = nota_extra(titulo, g["cat"])
        fim_ev = min(g["fim"], g["ini"] + timedelta(hours=6))
        extras[chave] = {
            "id": "g-" + hashlib.sha1("|".join(chave).encode()).hexdigest()[:10],
            "ini": g["ini"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "fim": fim_ev.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "g": grupo_extra(titulo, g["cat"]), "c": comp, "t": t, "n": "",
            "ch": [[g["canal"], "tv", "c"]], "s": estrelas(sc), "sc": sc,
            "_ini": g["ini"], "_tit": titulo,
        }
    for x in extras.values():
        del x["_ini"], x["_tit"]
    eventos += list(extras.values())
    eventos = [e for e in eventos if inicio <= datetime.fromisoformat(e["ini"].replace("Z", "+00:00")).astimezone(LISBOA) < fim]
    eventos.sort(key=lambda e: (e["ini"], -e["sc"]))

    dados = {
        "gerado": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "de": inicio.isoformat(), "ate": fim.isoformat(),
        "fontes": ["ESPN", "meuguia.tv"],
        "eventos": eventos,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    conf = sum(1 for e in eventos if any(c[2] == "c" for c in e["ch"]))
    print(f"OK: {len(eventos)} eventos ({len(extras)} extras, {conf} com canal confirmado, "
          f"{sem_canal} jogos da ESPN sem canal ficaram de fora)", file=sys.stderr)
    if not eventos:
        sys.exit("Nenhum evento: algo deu errado nas fontes.")


def traduz_fase(f):
    if not f:
        return ""
    t = f
    for a, b in [("Semifinals", "Semifinal"), ("Semifinal", "Semifinal"), ("Quarterfinals", "Quartas de final"),
                 ("Quarterfinal", "Quartas de final"), ("Round of 16", "Oitavas de final"), ("Final", "Final"),
                 ("1st Leg", "ida"), ("2nd Leg", "volta"), ("Leg 1", "ida"), ("Leg 2", "volta"),
                 ("Game", "Jogo"), ("Playoffs", "Playoffs"), ("Aggregate", "agregado")]:
        t = t.replace(a, b)
    return t


if __name__ == "__main__":
    main()
