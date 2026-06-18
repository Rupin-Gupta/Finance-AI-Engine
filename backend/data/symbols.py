"""Curated symbol lists: top 300 US (S&P 500 / NASDAQ 100) and top 400 Indian (NSE .NS).

yfinance format:
  - US stocks:    plain ticker  (AAPL, BRK-B)
  - Indian NSE:   ticker.NS     (RELIANCE.NS, M&M.NS)
"""

# ─── US Top ~300 ─────────────────────────────────────────────────────────────

US_SYMBOLS: list[str] = [
    # Mega-cap Technology
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "AMD",
    # Large-cap Tech
    "ORCL", "INTU", "CSCO", "IBM", "QCOM", "TXN", "ADI", "KLAC", "LRCX", "AMAT",
    "MCHP", "NXPI", "ON", "MRVL", "MPWR", "INTC", "SWKS", "TER", "KEYS", "MSI",
    "CRM", "ADBE", "NOW", "WDAY", "VEEV", "ADSK", "ANSS", "CDNS", "SNPS", "PTC",
    "DDOG", "CRWD", "ZS", "PANW", "FTNT", "ANET", "NET", "OKTA", "PLTR", "MDB",
    "SNOW", "DOCU", "ZM", "NTAP", "FFIV", "CTSH", "ZBRA", "ENPH",
    # Financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "V", "MA", "SCHW",
    "BLK", "BK", "STT", "USB", "COF", "DFS", "CB", "PGR", "TRV", "ALL",
    "AIG", "MET", "PRU", "AFL", "HIG", "MMC", "SPGI", "ICE", "CME", "NDAQ",
    "FIS", "FISV", "GPN", "PYPL", "AMP", "BX", "TROW", "RJF", "CBOE", "NU",
    # Healthcare
    "UNH", "LLY", "JNJ", "PFE", "ABT", "MRK", "ABBV", "BMY", "AMGN", "GILD",
    "VRTX", "REGN", "BIIB", "MRNA", "ISRG", "SYK", "MDT", "BSX", "EW", "ZBH",
    "HCA", "CI", "ELV", "HUM", "CVS", "MCK", "ZTS", "IDXX", "TMO", "IQV",
    "A", "HOLX", "DXCM", "RMD", "ALNY", "INCY", "RVTY", "ILMN", "BAX", "CRL",
    "ABC", "CAH", "DGX", "LH", "PODD", "ALGN", "UTHR", "NBIX", "JAZZ", "REGN",
    # Consumer Discretionary
    "COST", "WMT", "TGT", "HD", "LOW", "TJX", "ROST", "DG", "DLTR", "BBY",
    "MCD", "SBUX", "NKE", "DIS", "NFLX", "BKNG", "ABNB", "UBER", "GM", "F",
    "YUM", "CMG", "HLT", "MAR", "RIVN",
    # Consumer Staples
    "KO", "PEP", "PG", "MDLZ", "KMB", "CL", "GIS", "MO", "PM", "STZ",
    "WBA", "SYY", "HRL", "CAG",
    # Energy
    "XOM", "CVX", "COP", "EOG", "OXY", "MPC", "PSX", "VLO", "HAL", "SLB",
    "BKR", "FANG", "DVN", "KMI", "WMB", "OKE", "LNG", "HES", "MRO", "APA",
    # Industrials
    "GE", "HON", "CAT", "DE", "RTX", "LMT", "BA", "NOC", "GD", "ETN",
    "EMR", "ITW", "PH", "ROK", "GWW", "MMM", "UPS", "FDX", "NSC", "CSX",
    "UNP", "WM", "RSG", "CARR", "OTIS", "TDG", "HWM", "PCAR", "TT", "AME",
    "ROP", "IDEX", "IEX", "XYL", "IR",
    # Materials
    "LIN", "SHW", "ECL", "PPG", "NUE", "FCX", "DOW", "LYB", "APD", "ALB",
    "CE", "IFF", "FMC", "CTVA",
    # Utilities
    "NEE", "DUK", "SO", "AEP", "EXC", "D", "SRE", "ED", "WEC", "XEL",
    # Real Estate
    "PLD", "AMT", "EQIX", "CCI", "SPG", "O", "PSA", "WELL", "DLR", "AVB",
    # Communication Services
    "CMCSA", "CHTR", "VZ", "T", "TMUS", "WBD", "PARA",
    # Diversified / Other
    "BRK-B", "MSCI", "MCO", "BR", "ACN", "LDOS", "BAH", "SAIC", "GEHC",
    "FTV", "SQ", "LYFT", "SBAC", "WEX", "RGA", "EG", "VOYA", "EQR",
    "WRK", "IP", "PKG", "NWL", "SEE", "SON", "BEN", "IVZ", "MKTX", "ERIE",
]

# deduplicate preserving order
_seen: set[str] = set()
_us_dedup: list[str] = []
for _s in US_SYMBOLS:
    if _s not in _seen:
        _seen.add(_s)
        _us_dedup.append(_s)
US_SYMBOLS = _us_dedup


# ─── Indian NSE Top ~400 (.NS suffix) ────────────────────────────────────────

INDIA_SYMBOLS: list[str] = [
    # NIFTY 50
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFY.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "BAJFINANCE.NS", "KOTAKBANK.NS", "MARUTI.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "HCLTECH.NS", "TITAN.NS", "SUNPHARMA.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS", "TECHM.NS",
    "M&M.NS", "ADANIENT.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "TATACONSUM.NS", "NESTLEIND.NS", "DMART.NS", "BAJAJ-AUTO.NS",
    "BAJAJFINSV.NS", "BRITANNIA.NS", "GRASIM.NS", "HDFCLIFE.NS", "ICICIPRULI.NS",
    "INDUSINDBK.NS", "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS", "CIPLA.NS",
    "SBILIFE.NS", "VEDL.NS", "HINDALCO.NS", "BPCL.NS", "HEROMOTOCO.NS",
    "TRENT.NS",
    # NIFTY NEXT 50
    "APOLLOHOSP.NS", "PIDILITIND.NS", "SIEMENS.NS", "ABB.NS", "HAVELLS.NS",
    "MUTHOOTFIN.NS", "CHOLAFIN.NS", "DABUR.NS", "MARICO.NS", "GODREJCP.NS",
    "BERGEPAINT.NS", "COLPAL.NS", "JUBLFOOD.NS", "INDIGO.NS", "TATAPOWER.NS",
    "TORNTPHARM.NS", "LUPIN.NS", "BIOCON.NS", "AUROPHARMA.NS", "ALKEM.NS",
    "IPCALAB.NS", "SBICARD.NS", "ICICIGI.NS", "HDFCAMC.NS", "IRCTC.NS",
    "ZOMATO.NS", "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "BANKBARODA.NS",
    "CANBK.NS", "PNB.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "INDHOTEL.NS",
    "UPL.NS", "AMBUJACEM.NS", "ACC.NS", "SHREECEM.NS", "JSWENERGY.NS",
    "TATAELXSI.NS", "LTIM.NS", "LTTS.NS", "PERSISTENT.NS", "OFSS.NS",
    "MPHASIS.NS", "COFORGE.NS", "KPITTECH.NS", "CYIENT.NS", "NAUKRI.NS",
    # Mid-cap IT & Tech
    "HAPPSTMNDS.NS", "TANLA.NS", "ZENSARTECH.NS", "HEXAWARE.NS", "ROUTE.NS",
    "AFFLE.NS", "INDIAMART.NS", "MAPMYINDIA.NS", "JUSTDIAL.NS", "ANGELONE.NS",
    "CDSL.NS", "BSE.NS", "MCX.NS", "CAMS.NS", "KFINTECH.NS",
    # Pharma & Healthcare
    "LAURUSLABS.NS", "GRANULES.NS", "SYNGENE.NS", "GLAND.NS", "NATCOPHARM.NS",
    "AJANTPHARM.NS", "JBCHEPHARM.NS", "ERIS.NS", "METROPOLIS.NS", "THYROCARE.NS",
    "ABBOTINDIA.NS", "PFIZER.NS", "GLAXO.NS", "ZYDUSLIFE.NS", "CAPLIPOINT.NS",
    "SUVENPHAR.NS", "SEQUENT.NS", "SOLARA.NS", "DIVI.NS",
    # Banking & Finance
    "YESBANK.NS", "RBLBANK.NS", "AUBANK.NS", "BANDHANBNK.NS", "EQUITASBNK.NS",
    "UJJIVANSFB.NS", "CITYUNIONBNK.NS", "DCBBANK.NS", "SOUTHBANK.NS",
    "IIFL.NS", "MANAPPURAM.NS", "CANFINANCE.NS", "LICHSGFIN.NS", "HOMEFIRST.NS",
    "PNBHOUSING.NS", "APTUS.NS", "AAVAS.NS", "ABCAPITAL.NS", "CREDITACC.NS",
    "MOTILALOFS.NS", "ICICISEC.NS",
    # Insurance
    "STARHEALTH.NS", "NIACL.NS", "GICRE.NS", "MFSL.NS",
    # Power & Energy
    "ADANIPOWER.NS", "TORNTPOWER.NS", "CESC.NS", "NHPC.NS", "SJVN.NS",
    "TATAPOWER.NS", "RECLTD.NS", "PFC.NS", "IRFC.NS", "GAIL.NS",
    "PETRONET.NS", "HINDPETRO.NS", "IOCL.NS", "ADANIGAS.NS", "MRPL.NS",
    # Infrastructure & Logistics
    "RVNL.NS", "IRCON.NS", "RITES.NS", "BEL.NS", "HAL.NS",
    "COCHINSHIP.NS", "GRSE.NS", "MAZAGON.NS", "CONCOR.NS", "GMRINFRA.NS",
    "DELHIVERY.NS",
    # Auto & Auto Components
    "TVSMOTOR.NS", "ASHOKLEY.NS", "ESCORTS.NS", "FORCEMOT.NS", "MAHINDCIE.NS",
    "BHARATFORG.NS", "MOTHERSON.NS", "BOSCHLTD.NS", "EXIDEIND.NS", "AMARAJABAT.NS",
    "APOLLOTYRE.NS", "CEATLTD.NS", "BALKRISIND.NS", "JKTYRE.NS", "GOODYEAR.NS",
    "MRF.NS", "SUNDRMFAST.NS", "SCHAEFFLER.NS", "TIMKEN.NS", "SKFINDIA.NS",
    "UNOMINDA.NS", "SONACOMS.NS", "SUPRAJIT.NS",
    # Cement & Construction Materials
    "JKCEMENT.NS", "DALBHARAT.NS", "RAMCOCEM.NS", "HEIDELBERG.NS",
    "KAJARIACER.NS", "ASTRAL.NS", "SUPREMEIND.NS", "PRINCEPIPE.NS",
    "APLAPOLLO.NS", "RATNAMANI.NS", "POLYCAB.NS", "KEI.NS", "FINCABLES.NS",
    "CENTURYPLY.NS", "GREENLAM.NS",
    # Consumer & Retail
    "EMAMILTD.NS", "JYOTHYLAB.NS", "BAJAJCON.NS", "CASTROLIND.NS", "VSTIND.NS",
    "PAGEIND.NS", "RELAXO.NS", "BATAINDIA.NS", "METROBRAND.NS", "ABFRL.NS",
    "MANYAVAR.NS", "VMART.NS", "KALYANKJIL.NS", "SENCO.NS",
    # Hotels & Hospitality
    "LEMONTREE.NS", "CHALET.NS", "TAJGVK.NS",
    # Chemicals & Fertilisers
    "DEEPAKNTR.NS", "TATACHEM.NS", "GNFC.NS", "GSFC.NS", "COROMANDEL.NS",
    "CHAMBLFERT.NS", "NFL.NS", "PIIND.NS", "BAYER.NS", "DHANUKA.NS",
    "RALLIS.NS", "SUMICHEM.NS", "NAVINFLUOR.NS", "CLEAN.NS", "FLUOROCHEM.NS",
    "VINATIORGA.NS", "ALKYLAMINE.NS", "FINEORG.NS", "ROSSARI.NS",
    # Metals & Mining
    "NMDC.NS", "HINDZINC.NS", "NATIONALUM.NS", "HINDCOPPER.NS", "JSPL.NS",
    "SAIL.NS", "WELCORP.NS", "KIOCL.NS", "MOIL.NS",
    # Industrials & Engineering
    "THERMAX.NS", "CUMMINSIND.NS", "KEC.NS", "ENGINERSIN.NS", "AIAENG.NS",
    "GRINDWELL.NS", "CUMI.NS", "BHEL.NS", "TITAGARH.NS",
    # Real Estate
    "LODHA.NS", "PRESTIGE.NS", "BRIGADE.NS", "SOBHA.NS", "PHOENIXLTD.NS",
    "MAHLIFE.NS", "KOLTEPATIL.NS",
    # Textiles
    "VARDHMAN.NS", "TRIDENT.NS", "RAYMOND.NS", "ARVIND.NS", "KPRMILL.NS",
    "WELSPUNLIV.NS", "HIMATSEIDE.NS",
    # Media & Entertainment
    "ZEEL.NS", "PVRINOX.NS", "SAREGAMA.NS",
    # Telecom
    "TATACOMM.NS", "HFCL.NS", "STLTECH.NS", "TEJASNET.NS",
    # New-age / Digital
    "PAYTM.NS", "NYKAA.NS", "POLICYBZR.NS", "CARTRADE.NS", "EASEMYTRIP.NS",
    "SWIGGY.NS", "FIRSTCRY.NS",
    # Conglomerates
    "BAJAJHLDNG.NS", "TATAINVEST.NS", "GODREJIND.NS", "MCDOWELL-N.NS",
    # Miscellaneous Large / Mid
    "HONAUT.NS", "3MINDIA.NS", "GILLETTE.NS", "PGHH.NS",
    "LINDEINDIA.NS", "CRISIL.NS", "ICRA.NS", "CARERATING.NS",
    "VBL.NS", "HUDCO.NS", "IDEAFORGE.NS", "PARAS.NS",
    # Adani Group
    "ADANIGREEN.NS", "ADANITRANS.NS", "ADANITOTAL.NS",
    # Healthcare additional
    "ASTERDM.NS", "FORTIS.NS", "MAXHEALTH.NS", "RAINBOW.NS", "KIMS.NS",
    # Power & Renewables
    "IREDA.NS", "NTPCGREEN.NS",
    # Infrastructure
    "NBCC.NS", "BEML.NS", "KALPATPOWR.NS", "GPPL.NS",
    # Metals & Carbon
    "HEG.NS", "GRAPHITE.NS", "JINDALSAW.NS", "WELSPUNIND.NS", "PCBL.NS",
    "TINPLATE.NS", "TATACOFFEE.NS",
    # Consumer Electronics & Tech Hardware
    "DIXON.NS", "AMBER.NS", "KAYNES.NS", "SYRMA.NS", "CAMPUS.NS",
    # New listings / Digital
    "TATATECH.NS", "360ONE.NS", "LATENTVIEW.NS", "NUVAMA.NS", "BIKAJI.NS",
    "NUVOCO.NS", "CAMPUSACT.NS",
    # Retail & Lifestyle
    "SHOPERSTOP.NS", "TRENT.NS", "LANDMARK.NS",
    # Additional Finance
    "NSDL.NS", "IIFLSEC.NS",
    # Additional Auto
    "OLECTRA.NS", "TIINDIA.NS",
    # Additional Cement
    "JKLAKSHMI.NS",
    # Additional Chemicals
    "EPIGRAL.NS", "NOCIL.NS",
    # Additional Infra / Capital Goods
    "PTCIL.NS", "JINDALSTAINLESS.NS", "NSLNISP.NS",
    # Agri / FMCG
    "KRBL.NS", "LTFOODS.NS", "AVANTIFEED.NS", "WATERBASE.NS",
    # Media
    "BALAJITELE.NS", "NAZARA.NS",
    # Logistics
    "MAHLOG.NS", "BLUEDART.NS", "GATI.NS",
    # Additional Pharma
    "WINDLAS.NS", "MARKSANS.NS", "SPARC.NS", "GLENMARK.NS", "SUNPHARMA.NS",
    # Additional Banking
    "KTKBANK.NS", "IDBI.NS", "IOB.NS", "UCOBANK.NS", "MAHABANK.NS",
    # Additional Power
    "RELINFRA.NS", "JPPOWER.NS",
    # Additional IT
    "NIIT.NS", "MASTEK.NS", "MPHL.NS", "INTELLECT.NS", "NEWGEN.NS",
    # Additional Consumer
    "VSTIND.NS", "GODAWARI.NS", "IDFCFIRSTB.NS",
    # Additional Industrials
    "WABAG.NS", "PRAJ.NS", "ION.NS", "KENNAMETAL.NS",
    # Additional Real Estate
    "IBREALEST.NS", "MAHINDLIFE.NS", "KOLTEPATIL.NS", "SUNTECK.NS",
]

# deduplicate preserving order
_seen2: set[str] = set()
_in_dedup: list[str] = []
for _s in INDIA_SYMBOLS:
    if _s not in _seen2:
        _seen2.add(_s)
        _in_dedup.append(_s)
INDIA_SYMBOLS = _in_dedup

ALL_SYMBOLS: list[str] = US_SYMBOLS + INDIA_SYMBOLS
