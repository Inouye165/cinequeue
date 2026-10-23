"""Sports schedule and streaming availability service (NFL & NBA)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Catalog of major sports streaming services
STREAMING_SERVICES: list[dict[str, str]] = [
    {
        "id": "fox_one",
        "name": "FOX One (FOX Sports)",
        "short_name": "FOX One",
        "color": "#003366",
        "badge_bg": "#1e3a8a",
        "description": "NFL on FOX live games, FS1, FS2 & FOX Sports",
    },
    {
        "id": "peacock",
        "name": "Peacock",
        "short_name": "Peacock",
        "color": "#000000",
        "badge_bg": "#1e293b",
        "description": "NBC Sunday Night Football, NBA on NBC/Peacock",
    },
    {
        "id": "paramount_plus",
        "name": "Paramount+",
        "short_name": "Paramount+",
        "color": "#0064ff",
        "badge_bg": "#1d4ed8",
        "description": "NFL on CBS live local & national games",
    },
    {
        "id": "prime_video",
        "name": "Prime Video",
        "short_name": "Prime Video",
        "color": "#00a8e1",
        "badge_bg": "#0369a1",
        "description": "Thursday Night Football & NBA on Prime",
    },
    {
        "id": "espn_plus",
        "name": "ESPN+ / ESPN App",
        "short_name": "ESPN+",
        "color": "#cc0000",
        "badge_bg": "#b91c1c",
        "description": "Monday Night Football, NBA on ESPN & ABC simulcasts",
    },
    {
        "id": "max",
        "name": "Max (B/R Sports)",
        "short_name": "Max",
        "color": "#002be7",
        "badge_bg": "#3730a3",
        "description": "NBA on TNT live games via B/R Sports",
    },
    {
        "id": "youtube_tv",
        "name": "YouTube TV / Live TV",
        "short_name": "YouTube TV",
        "color": "#ff0000",
        "badge_bg": "#991b1b",
        "description": "FOX, CBS, NBC, ABC, ESPN, TNT, NBA TV, NFL Network",
    },
    {
        "id": "netflix",
        "name": "Netflix",
        "short_name": "Netflix",
        "color": "#e50914",
        "badge_bg": "#991b1b",
        "description": "NFL Christmas Day & special live events",
    },
    {
        "id": "nfl_plus",
        "name": "NFL+ / Sunday Ticket",
        "short_name": "NFL+",
        "color": "#013369",
        "badge_bg": "#1e3a8a",
        "description": "Live local/primetime mobile games & out-of-market NFL",
    },
    {
        "id": "nba_league_pass",
        "name": "NBA League Pass",
        "short_name": "League Pass",
        "color": "#1d428a",
        "badge_bg": "#1e40af",
        "description": "Out-of-market live NBA games",
    },
]

SERVICE_BY_ID: dict[str, dict[str, str]] = {s["id"]: s for s in STREAMING_SERVICES}

# Broadcast network to streaming service ID mapping
BROADCAST_TO_STREAMING: dict[str, list[str]] = {
    "NBC": ["peacock", "youtube_tv"],
    "PEACOCK": ["peacock"],
    "CBS": ["paramount_plus", "youtube_tv"],
    "PARAMOUNT+": ["paramount_plus"],
    "PRIME VIDEO": ["prime_video"],
    "AMAZON PRIME VIDEO": ["prime_video"],
    "AMZN": ["prime_video"],
    "ESPN": ["espn_plus", "youtube_tv"],
    "ESPN+": ["espn_plus"],
    "ESPN2": ["espn_plus", "youtube_tv"],
    "ABC": ["espn_plus", "youtube_tv"],
    "TNT": ["max", "youtube_tv"],
    "TRUTV": ["max", "youtube_tv"],
    "MAX": ["max"],
    "FOX": ["fox_one", "youtube_tv", "nfl_plus"],
    "FOX ONE": ["fox_one"],
    "FOX SPORTS": ["fox_one", "youtube_tv"],
    "FS1": ["fox_one", "youtube_tv"],
    "FS2": ["fox_one", "youtube_tv"],
    "FOX DEPORTES": ["fox_one", "youtube_tv"],
    "NFL NETWORK": ["nfl_plus", "youtube_tv"],
    "NFL NET": ["nfl_plus", "youtube_tv"],
    "NFL+": ["nfl_plus"],
    "NETFLIX": ["netflix"],
    "NBA TV": ["nba_league_pass", "youtube_tv"],
    "NBATV": ["nba_league_pass", "youtube_tv"],
    "NBA LEAGUE PASS": ["nba_league_pass"],
}

# Full catalog of 32 NFL teams and 30 NBA teams
TEAMS_CATALOG: list[dict[str, str]] = [
    # NFL (32 Teams)
    {"id": "nfl_ari", "league": "NFL", "abbr": "ARI", "name": "Arizona Cardinals", "short_name": "Cardinals", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png"},
    {"id": "nfl_atl", "league": "NFL", "abbr": "ATL", "name": "Atlanta Falcons", "short_name": "Falcons", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png"},
    {"id": "nfl_bal", "league": "NFL", "abbr": "BAL", "name": "Baltimore Ravens", "short_name": "Ravens", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png"},
    {"id": "nfl_buf", "league": "NFL", "abbr": "BUF", "name": "Buffalo Bills", "short_name": "Bills", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png"},
    {"id": "nfl_car", "league": "NFL", "abbr": "CAR", "name": "Carolina Panthers", "short_name": "Panthers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/car.png"},
    {"id": "nfl_chi", "league": "NFL", "abbr": "CHI", "name": "Chicago Bears", "short_name": "Bears", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png"},
    {"id": "nfl_cin", "league": "NFL", "abbr": "CIN", "name": "Cincinnati Bengals", "short_name": "Bengals", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png"},
    {"id": "nfl_cle", "league": "NFL", "abbr": "CLE", "name": "Cleveland Browns", "short_name": "Browns", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png"},
    {"id": "nfl_dal", "league": "NFL", "abbr": "DAL", "name": "Dallas Cowboys", "short_name": "Cowboys", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png"},
    {"id": "nfl_den", "league": "NFL", "abbr": "DEN", "name": "Denver Broncos", "short_name": "Broncos", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/den.png"},
    {"id": "nfl_det", "league": "NFL", "abbr": "DET", "name": "Detroit Lions", "short_name": "Lions", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png"},
    {"id": "nfl_gb", "league": "NFL", "abbr": "GB", "name": "Green Bay Packers", "short_name": "Packers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png"},
    {"id": "nfl_hou", "league": "NFL", "abbr": "HOU", "name": "Houston Texans", "short_name": "Texans", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png"},
    {"id": "nfl_ind", "league": "NFL", "abbr": "IND", "name": "Indianapolis Colts", "short_name": "Colts", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png"},
    {"id": "nfl_jax", "league": "NFL", "abbr": "JAX", "name": "Jacksonville Jaguars", "short_name": "Jaguars", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png"},
    {"id": "nfl_kc", "league": "NFL", "abbr": "KC", "name": "Kansas City Chiefs", "short_name": "Chiefs", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png"},
    {"id": "nfl_lv", "league": "NFL", "abbr": "LV", "name": "Las Vegas Raiders", "short_name": "Raiders", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png"},
    {"id": "nfl_lac", "league": "NFL", "abbr": "LAC", "name": "Los Angeles Chargers", "short_name": "Chargers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png"},
    {"id": "nfl_lar", "league": "NFL", "abbr": "LAR", "name": "Los Angeles Rams", "short_name": "Rams", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png"},
    {"id": "nfl_mia", "league": "NFL", "abbr": "MIA", "name": "Miami Dolphins", "short_name": "Dolphins", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png"},
    {"id": "nfl_min", "league": "NFL", "abbr": "MIN", "name": "Minnesota Vikings", "short_name": "Vikings", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/min.png"},
    {"id": "nfl_ne", "league": "NFL", "abbr": "NE", "name": "New England Patriots", "short_name": "Patriots", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png"},
    {"id": "nfl_no", "league": "NFL", "abbr": "NO", "name": "New Orleans Saints", "short_name": "Saints", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/no.png"},
    {"id": "nfl_nyg", "league": "NFL", "abbr": "NYG", "name": "New York Giants", "short_name": "Giants", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png"},
    {"id": "nfl_nyj", "league": "NFL", "abbr": "NYJ", "name": "New York Jets", "short_name": "Jets", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png"},
    {"id": "nfl_phi", "league": "NFL", "abbr": "PHI", "name": "Philadelphia Eagles", "short_name": "Eagles", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png"},
    {"id": "nfl_pit", "league": "NFL", "abbr": "PIT", "name": "Pittsburgh Steelers", "short_name": "Steelers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png"},
    {"id": "nfl_sf", "league": "NFL", "abbr": "SF", "name": "San Francisco 49ers", "short_name": "49ers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png"},
    {"id": "nfl_sea", "league": "NFL", "abbr": "SEA", "name": "Seattle Seahawks", "short_name": "Seahawks", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png"},
    {"id": "nfl_tb", "league": "NFL", "abbr": "TB", "name": "Tampa Bay Buccaneers", "short_name": "Buccaneers", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png"},
    {"id": "nfl_ten", "league": "NFL", "abbr": "TEN", "name": "Tennessee Titans", "short_name": "Titans", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png"},
    {"id": "nfl_wsh", "league": "NFL", "abbr": "WSH", "name": "Washington Commanders", "short_name": "Commanders", "logo": "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png"},

    # NBA (30 Teams)
    {"id": "nba_atl", "league": "NBA", "abbr": "ATL", "name": "Atlanta Hawks", "short_name": "Hawks", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/atl.png"},
    {"id": "nba_bos", "league": "NBA", "abbr": "BOS", "name": "Boston Celtics", "short_name": "Celtics", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"},
    {"id": "nba_bkn", "league": "NBA", "abbr": "BKN", "name": "Brooklyn Nets", "short_name": "Nets", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png"},
    {"id": "nba_cha", "league": "NBA", "abbr": "CHA", "name": "Charlotte Hornets", "short_name": "Hornets", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/cha.png"},
    {"id": "nba_chi", "league": "NBA", "abbr": "CHI", "name": "Chicago Bulls", "short_name": "Bulls", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png"},
    {"id": "nba_cle", "league": "NBA", "abbr": "CLE", "name": "Cleveland Cavaliers", "short_name": "Cavaliers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png"},
    {"id": "nba_dal", "league": "NBA", "abbr": "DAL", "name": "Dallas Mavericks", "short_name": "Mavericks", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/dal.png"},
    {"id": "nba_den", "league": "NBA", "abbr": "DEN", "name": "Denver Nuggets", "short_name": "Nuggets", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/den.png"},
    {"id": "nba_det", "league": "NBA", "abbr": "DET", "name": "Detroit Pistons", "short_name": "Pistons", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/det.png"},
    {"id": "nba_gs", "league": "NBA", "abbr": "GS", "name": "Golden State Warriors", "short_name": "Warriors", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/gs.png"},
    {"id": "nba_hou", "league": "NBA", "abbr": "HOU", "name": "Houston Rockets", "short_name": "Rockets", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/hou.png"},
    {"id": "nba_ind", "league": "NBA", "abbr": "IND", "name": "Indiana Pacers", "short_name": "Pacers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/ind.png"},
    {"id": "nba_lac", "league": "NBA", "abbr": "LAC", "name": "LA Clippers", "short_name": "Clippers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/lac.png"},
    {"id": "nba_lal", "league": "NBA", "abbr": "LAL", "name": "Los Angeles Lakers", "short_name": "Lakers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png"},
    {"id": "nba_mem", "league": "NBA", "abbr": "MEM", "name": "Memphis Grizzlies", "short_name": "Grizzlies", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/mem.png"},
    {"id": "nba_mia", "league": "NBA", "abbr": "MIA", "name": "Miami Heat", "short_name": "Heat", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png"},
    {"id": "nba_mil", "league": "NBA", "abbr": "MIL", "name": "Milwaukee Bucks", "short_name": "Bucks", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png"},
    {"id": "nba_min", "league": "NBA", "abbr": "MIN", "name": "Minnesota Timberwolves", "short_name": "Timberwolves", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/min.png"},
    {"id": "nba_no", "league": "NBA", "abbr": "NO", "name": "New Orleans Pelicans", "short_name": "Pelicans", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/no.png"},
    {"id": "nba_ny", "league": "NBA", "abbr": "NY", "name": "New York Knicks", "short_name": "Knicks", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/ny.png"},
    {"id": "nba_okc", "league": "NBA", "abbr": "OKC", "name": "Oklahoma City Thunder", "short_name": "Thunder", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/okc.png"},
    {"id": "nba_orl", "league": "NBA", "abbr": "ORL", "name": "Orlando Magic", "short_name": "Magic", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/orl.png"},
    {"id": "nba_phi", "league": "NBA", "abbr": "PHI", "name": "Philadelphia 76ers", "short_name": "76ers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/phi.png"},
    {"id": "nba_phx", "league": "NBA", "abbr": "PHX", "name": "Phoenix Suns", "short_name": "Suns", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/phx.png"},
    {"id": "nba_por", "league": "NBA", "abbr": "POR", "name": "Portland Trail Blazers", "short_name": "Trail Blazers", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/por.png"},
    {"id": "nba_sac", "league": "NBA", "abbr": "SAC", "name": "Sacramento Kings", "short_name": "Kings", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/sac.png"},
    {"id": "nba_sa", "league": "NBA", "abbr": "SA", "name": "San Antonio Spurs", "short_name": "Spurs", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/sa.png"},
    {"id": "nba_tor", "league": "NBA", "abbr": "TOR", "name": "Toronto Raptors", "short_name": "Raptors", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/tor.png"},
    {"id": "nba_utah", "league": "NBA", "abbr": "UTAH", "name": "Utah Jazz", "short_name": "Jazz", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/utah.png"},
    {"id": "nba_wsh", "league": "NBA", "abbr": "WSH", "name": "Washington Wizards", "short_name": "Wizards", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png"},
]

# Lookup helper for normalizing ESPN team abbreviations to our canonical team_id
TEAM_LOOKUP_BY_LEAGUE_ABBR: dict[tuple[str, str], dict[str, str]] = {}
for _t in TEAMS_CATALOG:
    TEAM_LOOKUP_BY_LEAGUE_ABBR[(_t["league"], _t["abbr"].upper())] = _t

# Alias abbreviations used by ESPN API
ESPN_ABBR_ALIASES: dict[tuple[str, str], str] = {
    ("NBA", "GSW"): "GS",
    ("NBA", "NYK"): "NY",
    ("NBA", "NOP"): "NO",
    ("NBA", "SAS"): "SA",
    ("NBA", "UTA"): "UTAH",
    ("NBA", "WAS"): "WSH",
    ("NFL", "WAS"): "WSH",
    ("NFL", "JAC"): "JAX",
}


def resolve_team(league: str, abbr: str, fallback_name: str = "") -> dict[str, str]:
    upper_abbr = (abbr or "").strip().upper()
    canonical_abbr = ESPN_ABBR_ALIASES.get((league, upper_abbr), upper_abbr)
    matched = TEAM_LOOKUP_BY_LEAGUE_ABBR.get((league, canonical_abbr))
    if matched:
        return matched
    # Fallback by name match
    lower_name = (fallback_name or "").lower()
    for t in TEAMS_CATALOG:
        if t["league"] == league and (t["name"].lower() == lower_name or t["short_name"].lower() in lower_name):
            return t
    return {
        "id": f"{league.lower()}_{upper_abbr.lower() or 'team'}",
        "league": league,
        "abbr": upper_abbr or "TBD",
        "name": fallback_name or upper_abbr or "TBD",
        "short_name": fallback_name or upper_abbr or "TBD",
        "logo": "",
    }


def map_broadcasts_to_services(league: str, broadcasts: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Map raw network names (e.g. ['NBC', 'Peacock']) to canonical streaming service IDs."""
    service_ids: list[str] = []
    normalized_networks: list[str] = []

    for b in broadcasts:
        for part in b.replace("/", ",").split(","):
            clean = part.strip()
            if clean and clean not in normalized_networks:
                normalized_networks.append(clean)
            upper = clean.upper()
            mapped = BROADCAST_TO_STREAMING.get(upper, [])
            for sid in mapped:
                if sid not in service_ids:
                    service_ids.append(sid)
            # Partial match heuristics
            if not mapped:
                if "ESPN" in upper and "espn_plus" not in service_ids:
                    service_ids.append("espn_plus")
                elif "PARAMOUNT" in upper or (league == "NFL" and upper == "CBS"):
                    if "paramount_plus" not in service_ids:
                        service_ids.append("paramount_plus")
                elif "PEACOCK" in upper or upper == "NBC":
                    if "peacock" not in service_ids:
                        service_ids.append("peacock")
                elif "PRIME" in upper or "AMAZON" in upper:
                    if "prime_video" not in service_ids:
                        service_ids.append("prime_video")
                elif "MAX" in upper or upper == "TNT":
                    if "max" not in service_ids:
                        service_ids.append("max")
                elif "NETFLIX" in upper:
                    if "netflix" not in service_ids:
                        service_ids.append("netflix")
                elif "FOX" in upper or upper in ("FS1", "FS2"):
                    if "fox_one" not in service_ids:
                        service_ids.append("fox_one")
                    if "youtube_tv" not in service_ids:
                        service_ids.append("youtube_tv")

    # Default league streaming services if regional/unmapped
    if league == "NBA" and "nba_league_pass" not in service_ids:
        # National exclusives like ESPN/ABC/TNT/Prime might still have League Pass or YouTube TV
        if not service_ids:
            service_ids.extend(["nba_league_pass", "youtube_tv"])
        elif "nba_league_pass" not in service_ids and not any(x in normalized_networks for x in ("ABC", "ESPN", "TNT", "Prime Video")):
            service_ids.append("nba_league_pass")
    elif league == "NFL" and not service_ids:
        service_ids.extend(["nfl_plus", "youtube_tv"])

    services = [SERVICE_BY_ID[sid] for sid in service_ids if sid in SERVICE_BY_ID]
    return normalized_networks or ([f"{league} Broadcast"] if league else []), services


def get_active_schedule_dates(now: datetime | None = None) -> list[date]:
    """Return active schedule dates: Today only, or Friday + Saturday + Sunday when today is Friday."""
    now_local = (now or datetime.now(timezone.utc)).astimezone()
    today = now_local.date()
    if today.weekday() == 4:  # Friday (0=Mon .. 4=Fri, 5=Sat, 6=Sun)
        return [today, today + timedelta(days=1), today + timedelta(days=2)]
    return [today]


def _build_fallback_games(now: datetime | None = None) -> list[dict[str, Any]]:
    """Build realistic upcoming NFL and NBA games within the active date window if live API is unreachable."""
    now_local = (now or datetime.now(timezone.utc)).astimezone()
    active_dates = get_active_schedule_dates(now_local)
    is_friday_weekend = len(active_dates) > 1

    # (league, home_id, home_rec, away_id, away_rec, day_offset, hour_local, networks, venue)
    matchups = [
        ("NBA", "nba_lal", "2-0", "nba_bos", "2-0", 0, 19, ["ESPN", "ABC"], "Crypto.com Arena"),
        ("NBA", "nba_gs", "1-1", "nba_den", "2-0", 0, 21, ["TNT", "Max"], "Chase Center"),
        ("NFL", "nfl_atl", "4-3", "nfl_sf", "4-3", 2 if is_friday_weekend else 0, 10, ["FOX", "FOX One"], "Mercedes-Benz Stadium"),
        ("NFL", "nfl_buf", "5-2", "nfl_bal", "5-2", 2 if is_friday_weekend else 0, 16, ["CBS", "Paramount+"], "Highmark Stadium"),
        ("NBA", "nba_ny", "1-1", "nba_mil", "1-1", 1 if is_friday_weekend else 0, 17, ["Prime Video", "NBA League Pass"], "Madison Square Garden"),
        ("NBA", "nba_phx", "2-0", "nba_okc", "2-0", 1 if is_friday_weekend else 0, 20, ["NBC", "Peacock"], "Footprint Center"),
        ("NFL", "nfl_det", "5-1", "nfl_gb", "5-2", 2 if is_friday_weekend else 0, 10, ["FOX", "FOX One"], "Ford Field"),
        ("NFL", "nfl_dal", "3-3", "nfl_phi", "4-2", 2 if is_friday_weekend else 0, 17, ["NBC", "Peacock"], "AT&T Stadium"),
    ]
    team_by_id = {t["id"]: t for t in TEAMS_CATALOG}
    games: list[dict[str, Any]] = []
    for idx, (league, home_id, home_rec, away_id, away_rec, day_offset, hour_local, networks, venue) in enumerate(matchups):
        target_date = active_dates[min(day_offset, len(active_dates) - 1)]
        start_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour_local,
            0,
            tzinfo=now_local.tzinfo,
        )
        home = team_by_id[home_id]
        away = team_by_id[away_id]
        norm_nets, services = map_broadcasts_to_services(league, networks)
        games.append({
            "id": f"fallback_{league.lower()}_{idx + 1}",
            "league": league,
            "title": f"{away['name']} at {home['name']}",
            "short_title": f"{away['abbr']} @ {home['abbr']}",
            "start_time": start_dt.isoformat(),
            "status": "scheduled",
            "status_detail": start_dt.strftime("%a, %b %d • %I:%M %p"),
            "is_live": False,
            "is_completed": False,
            "venue": venue,
            "home_team": {
                **home,
                "score": None,
                "record": home_rec,
            },
            "away_team": {
                **away,
                "score": None,
                "record": away_rec,
            },
            "broadcasts": norm_nets,
            "streaming_service_ids": [s["id"] for s in services],
            "streaming_services": services,
        })
    return games


def _parse_espn_events(league: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    events = data.get("events") or []
    parsed: list[dict[str, Any]] = []
    for ev in events:
        ev_id = str(ev.get("id") or "")
        competitions = ev.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0]
        competitors = comp.get("competitors") or []
        if len(competitors) < 2:
            continue

        home_raw = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_raw = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        def _extract_team(comp_entry: dict[str, Any]) -> dict[str, Any]:
            t_obj = comp_entry.get("team") or {}
            abbr = t_obj.get("abbreviation") or ""
            display_name = t_obj.get("displayName") or t_obj.get("name") or abbr
            canonical = resolve_team(league, abbr, display_name)
            records = comp_entry.get("records") or comp_entry.get("record") or []
            record_summary = ""
            if isinstance(records, list) and records:
                overall = next(
                    (
                        r for r in records
                        if isinstance(r, dict)
                        and (
                            str(r.get("type") or "").lower() == "total"
                            or str(r.get("name") or "").lower() in ("overall", "total", "all splits")
                        )
                    ),
                    records[0],
                )
                if isinstance(overall, dict):
                    record_summary = str(overall.get("summary") or overall.get("displayValue") or "").strip()
            if not record_summary:
                record_summary = "0-0"

            logos = t_obj.get("logos") or []
            logo_from_list = logos[0].get("href") if (isinstance(logos, list) and logos and isinstance(logos[0], dict)) else ""
            logo = str(canonical.get("logo") or t_obj.get("logo") or logo_from_list or "")
            raw_score = comp_entry.get("score")
            if isinstance(raw_score, dict):
                score_val = str(raw_score.get("displayValue") if raw_score.get("displayValue") is not None else (raw_score.get("value") or ""))
            elif raw_score is not None:
                score_val = str(raw_score)
            else:
                score_val = None
            team_color = str(t_obj.get("color") or "").strip("#")
            alt_color = str(t_obj.get("alternateColor") or "").strip("#")
            return {
                "id": canonical["id"],
                "league": league,
                "abbr": canonical["abbr"],
                "name": canonical["name"],
                "short_name": canonical["short_name"],
                "logo": logo,
                "score": score_val,
                "record": record_summary,
                "color": f"#{team_color}" if team_color else None,
                "alt_color": f"#{alt_color}" if alt_color else None,
            }

        home_team = _extract_team(home_raw)
        away_team = _extract_team(away_raw)

        # Broadcast extraction (supports both scoreboard 'names' and team schedule 'media.shortName')
        raw_broadcasts: list[str] = []
        for b in comp.get("broadcasts") or []:
            for name in b.get("names") or []:
                if name and name not in raw_broadcasts:
                    raw_broadcasts.append(name)
            media = b.get("media") or {}
            short_name = media.get("shortName")
            if short_name and short_name not in raw_broadcasts:
                raw_broadcasts.append(short_name)
        for gb in comp.get("geoBroadcasts") or []:
            media = gb.get("media") or {}
            short_name = media.get("shortName")
            if short_name and short_name not in raw_broadcasts:
                raw_broadcasts.append(short_name)

        norm_nets, services = map_broadcasts_to_services(league, raw_broadcasts)

        status_obj = comp.get("status") or ev.get("status") or {}
        status_type = status_obj.get("type") or {}
        state = (status_type.get("state") or "pre").lower()
        is_live = state == "in"
        is_completed = state == "post" or bool(status_type.get("completed"))
        status_detail = status_type.get("shortDetail") or status_type.get("detail") or "Scheduled"

        venue_obj = comp.get("venue") or {}
        venue_name = venue_obj.get("fullName") or ""

        start_date = comp.get("date") or ev.get("date") or datetime.now(timezone.utc).isoformat()

        parsed.append({
            "id": f"{league.lower()}_{ev_id}",
            "league": league,
            "title": f"{away_team['name']} at {home_team['name']}",
            "short_title": f"{away_team['abbr']} @ {home_team['abbr']}",
            "start_time": start_date,
            "status": "live" if is_live else ("completed" if is_completed else "scheduled"),
            "status_detail": status_detail,
            "is_live": is_live,
            "is_completed": is_completed,
            "venue": venue_name,
            "home_team": home_team,
            "away_team": away_team,
            "broadcasts": norm_nets,
            "streaming_service_ids": [s["id"] for s in services],
            "streaming_services": services,
        })
    return parsed


class SportsService:
    """Fetches and caches live NFL & NBA schedules with streaming service mappings."""

    def __init__(self, cache_ttl_seconds: int = 600) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._cached_games_by_key: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def get_catalog(self) -> dict[str, Any]:
        return {
            "leagues": ["NFL", "NBA"],
            "streaming_services": STREAMING_SERVICES,
            "teams": TEAMS_CATALOG,
        }

    async def get_schedule(
        self,
        tracked_teams: list[str] | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        now_local = datetime.now(timezone.utc).astimezone()
        active_dates = get_active_schedule_dates(now_local)
        active_date_strs = [d.strftime("%Y%m%d") for d in active_dates]
        cache_key = ",".join(active_date_strs)
        now_ts = time.time()

        if not force_refresh and cache_key in self._cached_games_by_key:
            cached_ts, cached_list = self._cached_games_by_key[cache_key]
            if cached_list and (now_ts - cached_ts < self._cache_ttl):
                return cached_list

        games_by_id: dict[str, dict[str, Any]] = {}
        urls: list[tuple[str, str]] = []
        for date_str in active_date_strs:
            urls.append(("NFL", f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date_str}"))
            urls.append(("NBA", f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"))

        async def _fetch_one(client: httpx.AsyncClient, league: str, url: str) -> list[dict[str, Any]]:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return _parse_espn_events(league, resp.json())
            except Exception as exc:
                logger.warning("Failed to fetch %s schedule from %s: %s", league, url, exc)
            return []

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                results = await asyncio.gather(*(_fetch_one(client, lg, u) for lg, u in urls))
                for league_games in results:
                    for g in league_games:
                        games_by_id[g["id"]] = g
        except Exception as exc:
            logger.warning("HTTP client error fetching sports schedule: %s", exc)

        active_dates_set = set(active_dates)
        filtered_games: list[dict[str, Any]] = []
        for g in games_by_id.values():
            try:
                dt = datetime.fromisoformat(str(g["start_time"]).replace("Z", "+00:00")).astimezone(now_local.tzinfo)
                if dt.date() in active_dates_set:
                    filtered_games.append(g)
            except Exception:
                filtered_games.append(g)

        games = filtered_games
        if not games:
            games = _build_fallback_games(now_local)

        # Sort live games first, then upcoming by start_time, then completed last
        def _sort_key(g: dict[str, Any]) -> tuple[int, str]:
            rank = 0 if g.get("is_live") else (2 if g.get("is_completed") else 1)
            return (rank, g.get("start_time") or "")

        games.sort(key=_sort_key)
        self._cached_games_by_key[cache_key] = (now_ts, games)
        return games


sports_service = SportsService()
