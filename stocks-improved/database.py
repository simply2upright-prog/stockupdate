# database.py — Verbessert: Regionen-Währungs-Mapping, saubere Duplikatentfernung, sortierte Liste

TICKER_LISTS = {
    "ENERGY_OIL_GAS": [
        "PBR", "OXY", "XOM", "CVX", "SHEL.L", "BP.L", "TTE.PA", "EQNR",
        "AKRBP.OL", "VAR.OL", "DNO.OL", "COP", "EOG", "SLB", "HAL",
        "MPC", "PSX", "VLO", "DVN", "FANG", "APA", "CTRA", "CHRD",
        "MTDR", "PR", "SM", "OMV.VI", "HBR.L"
    ],
    "UTILITIES_INFRASTRUCTURE": [
        "VIE.PA", "ENGI.PA", "IBE.MC", "ENEL.MI", "EDP.LS", "ENG.MC",
        "REE.MC", "TER.MI", "NG.L", "UU.L", "SVE.PA", "RWE.DE",
        "EOAN.DE", "NEE", "DUK", "SO", "D", "AEP", "SRE", "AWK"
    ],
    "REAL_ESTATE_CONSTRUCTION_EUROPE": [
        "VNA.DE", "LEG.DE", "HOT.DE", "TAG.DE", "DWNI.DE",
        "DG.PA", "SGO.PA", "EN.PA", "LI.PA", "URW.PA",
        "BDEV.L", "PSN.L", "TW.L", "BLND.L", "SGRO.L", "LAND.L", "BKG.L",
        "ACS.MC", "FER.MC", "SKAB.ST", "SBB-B.ST"
    ],
    "SIN_STOCKS_SWEETS_ENERGY": [
        "PM", "MO", "BTI", "BATS.L", "IMB.L", "2914.T", "UVV",
        "DEO", "RI.PA", "BF-B", "STZ", "BUD", "HEIA.AS", "HEIO.AS",
        "CARL-B.CO", "TAP", "CAMP.MI", "2501.T", "LVMH.PA",
        "MDLZ", "BN.PA", "UMG.AS", "DIS", "HSY", "NESN.SW", "LINDT.SW",
        "MNST", "CELH", "KDP"
    ],
    "DAX": [
        "ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE",
        "BMW.DE", "CBK.DE", "CON.DE", "1COV.DE", "DTG.DE", "DBK.DE",
        "DB1.DE", "DHL.DE", "DTE.DE", "EOAN.DE", "ENR.DE", "FRE.DE",
        "HEI.DE", "HEN3.DE", "HNR1.DE", "IFX.DE", "MBG.DE", "MRK.DE",
        "MTX.DE", "MUV2.DE", "P911.DE", "PAH3.DE", "PUM.DE", "RHM.DE",
        "RWE.DE", "SAP.DE", "SRT3.DE", "SHL.DE", "SIE.DE", "SY1.DE",
        "TKA.DE", "VNA.DE", "VOW3.DE", "ZAL.DE"
    ],
    "MDAX": [
        "BC8.DE", "BNR.DE", "BOSS.DE", "DEQ.DE", "DUE.DE", "EVD.DE",
        "EVK.DE", "FPE.DE", "FRA.DE", "FME.DE", "GXI.DE", "HNR1.DE",
        "HHE.DE", "HOT.DE", "JUN3.DE", "KRN.DE", "LAN.DE", "LEG.DE",
        "NDX1.DE", "NEM.DE", "PUM.DE", "RHM.DE", "SAF.DE", "SDF.DE",
        "SIX2.DE", "SZG.DE", "TAG.DE", "TKA.DE", "TLX.DE", "VNA.DE",
        "WAF.DE", "WCH.DE", "ZAL.DE"
    ],
    "SDAX": [
        "1U1.DE", "B7A.DE", "BC8.DE", "BIL.DE", "BVB.DE", "C3X.DE",
        "CEC.DE", "DEQ.DE", "DIC.DE", "DUE.DE", "DWNI.DE", "EVD.DE",
        "FIE.DE", "FRA.DE", "FNTN.DE", "GFT.DE", "GNL.DE", "HHFA.DE",
        "HLAG.DE", "HDD.DE", "HORN.DE", "IVU.DE", "JEN.DE", "JOST.DE",
        "JUN3.DE", "KLO.DE", "KRN.DE", "KWS.DE", "MLP.DE", "NDX1.DE",
        "O2D.DE", "PBB.DE", "PNE3.DE", "PSM.DE", "QIA.DE", "SAF.DE",
        "SDF.DE", "SOW.DE", "STR.DE", "SY1.DE", "TAG.DE", "TTK.DE",
        "VAR1.DE", "VIP.DE", "WAF.DE", "WCH.DE", "WUW.DE"
    ],
    "EURO_STOXX_50": [
        "AD.AS", "AI.PA", "AIR.PA", "ALV.DE", "ASML.AS", "CS.PA",
        "BAS.DE", "BAYN.DE", "BBVA.MC", "SAN.MC", "BMW.DE", "BNP.PA",
        "BN.PA", "DHL.DE", "DTE.DE", "ENEL.MI", "ENI.MI", "EL.PA",
        "STLA.PA", "IBE.MC", "ITX.MC", "IFX.DE", "INGA.AS", "ISP.MI",
        "KER.PA", "KNEBV.HE", "OR.PA", "MC.PA", "MBG.DE", "MUV2.DE",
        "RI.PA", "PRX.AS", "SAF.PA", "SGO.PA", "SAN.PA", "SAP.DE",
        "SU.PA", "SIE.DE", "TTE.PA", "DG.PA", "VOW3.DE", "VNA.DE",
        "WKL.AS", "HER.PA", "RACE.MI", "UCG.MI", "ENGI.PA", "VIE.PA",
        "ADS.DE", "ASML", "FLTR.L"
    ],
    "MINING_CYCLICALS": [
        "RIO", "RIO.L", "BHP", "VALE", "GLNCY", "GLEN.L", "AAUKF",
        "FCX", "NEM", "GOLD", "AEM", "GFI", "ALB", "SQM", "CCJ",
        "CAT", "DE", "MMM", "GE", "HON", "LMT", "BA", "UPS", "FDX",
        "NSC", "UNP", "EMR", "ETN", "ITW", "DOW", "LYB", "CTVA",
        "NUE", "STLD", "AA", "CF", "MOS", "F", "GM", "STLA"
    ],
    "NASDAQ_GROWTH_TECH": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
        "AVGO", "NFLX", "ADBE", "AMD", "QCOM", "TXN", "INTU", "AMAT",
        "ISRG", "BKNG", "VRTX", "PANW", "MU", "SNPS", "CDNS", "KLAC",
        "MELI", "PYPL", "SNOW", "PLTR", "SMCI", "VRT", "DECK", "ANF",
        "SOFI", "AFRM", "COIN", "DKNG"
    ],
    "EURO_UK_STOCKS": [
        "ASML", "MC.PA", "OR.PA", "RMS.PA", "KER.PA", "NOVN.SW",
        "ROG.SW", "LIN", "SAN.MC", "IBE.MC", "ITX.MC", "ENI.MI",
        "RACE.MI", "AZN.L", "HSBA.L", "ULVR.L", "GSK.L", "RIO.L"
    ],
    "HEALTHCARE_PHARMA": [
        "JNJ", "PFE", "ABBV", "LLY", "MRK", "NVO", "AZN", "GSK",
        "SYK", "UNH"
    ],
    "CONSUMER_STAPLES": [
        "PG", "KO", "PEP", "WMT", "COST", "NSRGY", "UL", "CL", "KHC", "EL"
    ],
    "FINANCIALS_PAYMENTS": [
        "JPM", "BAC", "V", "MA", "AXP", "BLK", "MS", "GS", "HSBC"
    ],
    "REITS_REAL_ESTATE": [
        "O", "AMT", "PLD", "CCI", "SPG", "VICI", "DLR", "PSA"
    ],
}

# --- WÄHRUNGS-MAPPING nach Suffix ---
# Wird in app.py genutzt, um das richtige Währungssymbol anzuzeigen
CURRENCY_MAP = {
    ".DE": "€", ".PA": "€", ".MC": "€", ".MI": "€", ".AS": "€",
    ".VI": "€", ".LS": "€", ".HE": "€",
    ".L":  "£",
    ".SW": "CHF",
    ".OL": "NOK",
    ".ST": "SEK",
    ".CO": "DKK",
    ".T":  "¥",
    # Kein Suffix = US-Dollar
}

def get_currency(ticker: str) -> str:
    """Gibt das Währungssymbol für einen Ticker zurück."""
    for suffix, symbol in CURRENCY_MAP.items():
        if ticker.upper().endswith(suffix.upper()):
            return symbol
    return "$"  # Default: US-Dollar

def get_all_tickers() -> list[str]:
    """Gibt alle einzigartigen Ticker sortiert zurück."""
    seen = set()
    result = []
    for tickers in TICKER_LISTS.values():
        for t in tickers:
            if t not in seen:
                seen.add(t)
                result.append(t)
    return sorted(result)

def get_tickers_by_group(group: str) -> list[str]:
    """Gibt die Ticker einer bestimmten Gruppe zurück."""
    return TICKER_LISTS.get(group, [])

def get_all_groups() -> list[str]:
    """Gibt alle Gruppen-Namen zurück."""
    return list(TICKER_LISTS.keys())
