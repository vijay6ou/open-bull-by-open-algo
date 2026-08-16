"""Jainam XTS master-contract download into OpenBull's shared symtoken table."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.broker.jainamxts.baseurl import MARKET_DATA_URL
from backend.broker.jainamxts.xts_auth import split_auth
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)

TMP_DIR = Path(__file__).resolve().parents[4] / "tmp"
TMP_DIR.mkdir(exist_ok=True)

_frames: list[pd.DataFrame] = []


def _build_isolated_engine_and_session():
    from backend.config import get_settings
    engine = create_async_engine(get_settings().database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _auth_headers(auth_token: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        _, feed, _ = split_auth(auth_token)
        token = feed or split_auth(auth_token)[0]
        if token:
            headers["authorization"] = token
    return headers


def copy_from_dataframe(df):
    """Accumulate processed frames; the download entry-point inserts once."""
    if df is None or df.empty:
        return
    _frames.append(df)


_AUTH_TOKEN: str | None = None


def download_csv_jainamxts_data(output_path):
    logger.info("Downloading Master Contract CSV Files")
    exchange_segments = ["NSECM", "NSEFO", "BSECM", "BSEFO"]
    headers_equity = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low, FreezeQty,TickSize,LotSize,Multiplier,DisplayName,ISIN,PriceNumerator,PriceDenominator,DetailedDescription,ExtendedSurvIndicator,CautionIndicator,GSMIndicator\n"
    headers_fo = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low,FreezeQty,TickSize,LotSize,Multiplier,UnderlyingInstrumentId,UnderlyingIndexName,ContractExpiration,StrikePrice,OptionType,DisplayName, PriceNumerator,PriceDenominator,DetailedDescription\n"

    # Get the shared httpx client with connection pooling
    client = get_httpx_client()
    headers = _auth_headers(_AUTH_TOKEN)

    downloaded_files = []
    for segment in exchange_segments:
        payload = json.dumps({"exchangeSegmentList": [segment]})
        response = client.post(
            f"{MARKET_DATA_URL}/instruments/master", headers=headers, content=payload
        )
        if response.status_code != 200:
            raise Exception(f"Failed to download {segment}. Status: {response.status_code}")

        data = response.json()
        if "result" not in data:
            raise Exception(f"Invalid response format for {segment}: Missing 'result' field")

        if segment in ["NSECM", "BSECM"]:
            header = headers_equity
        else:
            header = headers_fo

        segment_output_path = f"{output_path}/{segment}.csv"
        os.makedirs(output_path, exist_ok=True)

        csv_data = data["result"].split("\n")  # Convert result string to list of rows
        csv_data = [
            row.split("|") for row in csv_data if row.strip()
        ]  # Convert each row into a list

        with open(segment_output_path, "w", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header.strip().split(","))  # Write headers
            writer.writerows(csv_data)
        downloaded_files.append(segment_output_path)


def fetch_index_list():
    logger.info("Fetching Index List")
    exchange_segments = [1, 11]  # NSE and BSE indexes
    headers = _auth_headers(_AUTH_TOKEN)

    # Get the shared httpx client with connection pooling
    client = get_httpx_client()
    index_data = []

    for segment in exchange_segments:
        url = f"{MARKET_DATA_URL}/instruments/indexlist?exchangeSegment={segment}"
        response = client.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch index list for segment {segment}. Status: {response.status_code}"
            )
            continue

        data = response.json()
        logger.debug(f"Index list response for segment {segment}: {data}")

        if "result" not in data or "indexList" not in data["result"]:
            logger.error(f"Invalid response format for segment {segment}: {data}")
            continue

        for index_entry in data["result"]["indexList"]:
            # Extract symbol name and token
            symbol_name, token = index_entry.rsplit("_", 1)

            index_data.append(
                {
                    "brsymbol": index_entry,  # Full format (e.g., "NIFTY 100_26004")
                    "symbol": symbol_name,  # Raw symbol before mapping
                    "exchange": "NSE_INDEX" if segment == 1 else "BSE_INDEX",
                    "token": token,
                }
            )

    return index_data


def reformat_symbol_detail(s):
    parts = s.split()  # Split the string into parts
    # Reorder and format the parts to match the desired output
    # Assuming the format is consistent and always "Name DD Mon YY FUT"
    return f"{parts[0]}{parts[3]}{parts[2].upper()}{parts[1]}{parts[4]}"


# Shared BSE index normalization map used by both BSECM SPOT ingestion
# and indexlist ingestion paths.
BSE_INDEX_SYMBOL_MAP = {
    "SNSX50": "SENSEX50",
    "SNXT50": "BSESENSEXNEXT50",
    "MID150": "BSE150MIDCAPINDEX",
    "LMI250": "BSE250LARGEMIDCAPINDEX",
    "MSL400": "BSE400MIDSMALLCAPINDEX",
    "AUTO": "BSEAUTO",
    "BSE CG": "BSECAPITALGOODS",
    "CARBON": "BSECARBONEX",
    "BSE CD": "BSECONSUMERDURABLES",
    "CPSE": "BSECPSE",
    "DOL100": "BSEDOLLEX100",
    "DOL200": "BSEDOLLEX200",
    "DOL30": "BSEDOLLEX30",
    "ENERGY": "BSEENERGY",
    "BSEFMC": "BSEFASTMOVINGCONSUMERGOODS",
    "FIN": "BSEFINANCIALSERVICES",
    "FINSER": "BSEFINANCIALSERVICES",
    "GREENX": "BSEGREENEX",
    "BSE HC": "BSEHEALTHCARE",
    "INFRA": "BSEINDIAINFRASTRUCTUREINDEX",
    "INDSTR": "BSEINDUSTRIALS",
    "BSE IT": "BSEINFORMATIONTECHNOLOGY",
    "LRGCAP": "BSELARGECAP",
    "METAL": "BSEMETAL",
    "MIDCAP": "BSEMIDCAP",
    "MIDSEL": "BSEMIDCAPSELECTINDEX",
    "OILGAS": "BSEOIL&GAS",
    "POWER": "BSEPOWER",
    "BSEPBI": "BSEPSU",
    "REALTY": "BSEREALTY",
    "SMLCAP": "BSESMALLCAP",
    "SMLSEL": "BSESMALLCAPSELECTINDEX",
    "SMEIPO": "BSESMEIPO",
    "TECK": "BSETECK",
    "TELCOM": "BSETELECOM",
}


def normalize_bse_index_symbols(symbol_series: pd.Series) -> pd.Series:
    """Normalize raw BSE index symbols to OpenAlgo naming and format."""
    normalized = symbol_series.astype(str).str.upper().str.strip()
    normalized = normalized.str.replace(r"\s+", " ", regex=True)
    normalized = normalized.replace(BSE_INDEX_SYMBOL_MAP)
    return normalized.str.replace(r"[\s\-]+", "", regex=True)


def process_jainamxts_nse_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS NSE CSV Data")
    file_path = f"{path}/NSECM.csv"

    df = pd.read_csv(file_path)

    df = df[df["Series"].isin(["EQ"])]

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"]
    token_df["brsymbol"] = df["DisplayName"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = df["ExchangeSegment"].map({"NSECM": "NSE"})
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"]
    token_df["expiry"] = ""
    token_df["strike"] = 1.0
    token_df["lotsize"] = df["LotSize"]
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = df["TickSize"]

    return token_df


def process_jainamxts_bse_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS BSE CSV Data")
    file_path = f"{path}/BSECM.csv"

    df = pd.read_csv(file_path)

    # df = df[df['Series'].isin(['EQ'])]

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"]
    token_df["brsymbol"] = df["DisplayName"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = df.apply(
        lambda row: "BSE_INDEX" if row["Series"] == "SPOT" else "BSE", axis=1
    )
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"]
    token_df["expiry"] = ""
    token_df["strike"] = 1.0
    token_df["lotsize"] = df["LotSize"]
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = df["TickSize"]

    # Normalize BSE index short codes from SPOT rows to OpenAlgo index symbols
    bse_idx_mask = token_df["exchange"] == "BSE_INDEX"
    token_df.loc[bse_idx_mask, "symbol"] = normalize_bse_index_symbols(
        token_df.loc[bse_idx_mask, "symbol"]
    )
    token_df.loc[bse_idx_mask, "name"] = token_df.loc[bse_idx_mask, "symbol"]

    return token_df


def process_jainamxts_nfo_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS NFO CSV Data")
    file_path = f"{path}/NSEFO.csv"

    df = pd.read_csv(
        file_path, dtype={"StrikePrice": str, " PriceNumerator": str}, low_memory=False
    )

    # Convert 'Expiry Date' column to datetime format
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])

    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    # Create token_df with the relevant columns
    token_df = df[["symbol"]].copy()
    token_df["symbol"] = df["symbol"].values
    token_df["brsymbol"] = df["Description"].values
    token_df["name"] = df["Name"].values
    token_df["exchange"] = df["ExchangeSegment"].map({"NSEFO": "NFO"})
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].values

    # Convert 'Expiry Date' to desired format
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"].values
    token_df["lotsize"] = df["LotSize"].values
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"})
    token_df["tick_size"] = df["TickSize"].values

    return token_df


def process_jainamxts_cds_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS CDS CSV Data")
    file_path = f"{path}/NSECD.csv"

    df = pd.read_csv(file_path)

    df = df.dropna(subset=["OptionType"])

    if df.empty:
        logger.info("No CDS data available, skipping")
        return pd.DataFrame()

        # Convert 'Expiry Date' column to datetime format
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])

    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    # Generate symbols based on instrument type
    # df['symbol'] = df.apply(lambda x:
    #    f"{x['Name']}{x['ContractExpiration'].strftime('%d%b%y').upper()}{'FUT' if x['OptionType']=='1' else str(int(float(x['StrikePrice'])))+('CE' if x['OptionType']=='3' else 'PE')}",
    #    axis=1
    # )
    # Remove any rows where symbol generation failed
    # df = df[df['symbol'].notna()]

    # Create token_df with the relevant columns
    token_df = df[["symbol"]].copy()
    token_df["symbol"] = df["symbol"].values
    token_df["brsymbol"] = df["Description"].values
    token_df["name"] = df["Name"].values
    token_df["exchange"] = df["ExchangeSegment"].map({"NSECD": "CDS"})
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].values

    # Convert 'Expiry Date' to desired format
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"].values
    token_df["lotsize"] = df["LotSize"].values
    token_df["instrumenttype"] = token_df["symbol"].apply(
        lambda x: "FUT" if "FUT" in x else ("PE" if "PE" in x else "CE")
    )
    # token_df['instrumenttype'] = df['OptionType'].map({
    #        1: 'FUT',
    #        872604 : 'FUT',
    #        5892 : 'FUT',
    #        3: 'CE',
    #        4: 'PE'
    #    })
    token_df["tick_size"] = df["TickSize"].values

    return token_df


def process_jainamxts_bfo_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS BFO CSV Data")
    file_path = f"{path}/BSEFO.csv"

    df = pd.read_csv(
        file_path, dtype={"StrikePrice": str, " PriceNumerator": str}, low_memory=False
    )

    # Convert 'Expiry Date' column to datetime format
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])

    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    token_df = df[["symbol"]].copy()
    token_df["symbol"] = df["symbol"].values
    token_df["brsymbol"] = df["Description"].values
    token_df["name"] = df["Name"].values
    token_df["exchange"] = df["ExchangeSegment"].map({"BSEFO": "BFO"})
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].values

    # Convert 'Expiry Date' to desired format
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"].values
    token_df["lotsize"] = df["LotSize"].values
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"})
    token_df["tick_size"] = df["TickSize"].values

    return token_df


def process_jainamxts_mcx_csv(path):
    """
    Processes the JainamXTS CSV file to fit the existing database schema and performs exchange name mapping.
    """
    logger.info("Processing JainamXTS MCX CSV Data")
    file_path = f"{path}/MCXFO.csv"

    df = pd.read_csv(file_path)

    # Drop rows where the 'Exch Seg' column has the value 'COMTDY'
    df = df[df["ContractExpiration"] != "1"]

    if df.empty:
        logger.info("No MCX data available, skipping")
        return pd.DataFrame()

    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])
    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    # Create token_df with the relevant columns
    token_df = df[["symbol"]].copy()
    token_df["symbol"] = df["symbol"].values
    token_df["brsymbol"] = df["Description"].values
    token_df["name"] = df["Name"].values
    token_df["exchange"] = df["ExchangeSegment"].map({"MCXFO": "MCX"})
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].values

    # Convert 'Expiry Date' to desired format
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"].values
    token_df["lotsize"] = df["LotSize"].values
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"})
    token_df["tick_size"] = df["TickSize"].values

    return token_df


def process_index_data(index_data):
    """
    Processes index data from API to fit the OpenAlgo database schema.
    Uses regex normalization to handle spacing variations in symbol names.

    Input format from API (index_entry format: "SYMBOL_TOKEN"):
    - brsymbol: Full format (e.g., "NIFTY 100_26004")
    - symbol: Raw symbol before mapping (e.g., "NIFTY 100")
    - exchange: NSE_INDEX or BSE_INDEX
    - token: Token value
    """
    logger.info("Processing Index Data")
    df = pd.DataFrame(index_data)
    if df.empty:
        return df

    # Normalize casing and spacing first
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["symbol"] = df["symbol"].str.replace(r"\s+", " ", regex=True)

    # NSE index mapping (raw broker index names -> OpenAlgo symbols)
    nse_index_map = {
        "NIFTY 50": "NIFTY",
        "NIFTY BANK": "BANKNIFTY",
        "INDIA VIX": "INDIAVIX",
        "NIFTY FIN SERVICE": "FINNIFTY",
        "NIFTY MID SELECT": "MIDCPNIFTY",
        "NIFTY NEXT 50": "NIFTYNXT50",
        "HANGSENG BEES NAV": "HANGSENGBEESNAV",
        "HANGSENG BEES-NAV": "HANGSENGBEESNAV",
    }
    df["symbol"] = df["symbol"].replace(nse_index_map)

    # BSE short-code mapping (applied only to BSE_INDEX symbols)
    bse_idx_mask = df["exchange"] == "BSE_INDEX"
    df.loc[bse_idx_mask, "symbol"] = normalize_bse_index_symbols(
        df.loc[bse_idx_mask, "symbol"]
    )

    # Final cleanup: enforce no spaces/hyphens in symbols
    df["symbol"] = df["symbol"].str.replace(r"[\s\-]+", "", regex=True)

    df["name"] = df["symbol"]
    df["brexchange"] = df["exchange"]
    df["expiry"] = ""
    df["strike"] = 1.0
    df["lotsize"] = 1  # Default index lot size
    df["instrumenttype"] = "INDEX"
    df["tick_size"] = 0.05

    return df


def delete_jainamxts_temp_data(output_path):
    if not os.path.isdir(output_path):
        return
    for filename in os.listdir(output_path):
        file_path = os.path.join(output_path, filename)
        if filename.endswith(".csv") and os.path.isfile(file_path):
            os.remove(file_path)
            logger.info("Deleted %s", file_path)


def _nan_to_none(rows: list[dict]) -> list[dict]:
    for row in rows:
        for k, v in row.items():
            if isinstance(v, float) and math.isnan(v):
                row[k] = None
            elif hasattr(v, "item"):
                try:
                    row[k] = v.item()
                except Exception:
                    pass
        if row.get("token") is not None:
            row["token"] = str(row["token"])
        if row.get("lotsize") is not None:
            try:
                row["lotsize"] = int(row["lotsize"])
            except (TypeError, ValueError):
                row["lotsize"] = None
    return rows


def master_contract_download(auth_token: str | None = None) -> dict:
    """Download Jainam XTS master contracts and populate symtoken."""
    global _AUTH_TOKEN, _frames
    _AUTH_TOKEN = auth_token
    _frames = []
    output_path = str(TMP_DIR)

    try:
        download_csv_jainamxts_data(output_path)

        processors = (
            process_jainamxts_nse_csv,
            process_jainamxts_bse_csv,
            process_jainamxts_nfo_csv,
            process_jainamxts_bfo_csv,
            process_jainamxts_cds_csv,
            process_jainamxts_mcx_csv,
        )
        for processor in processors:
            try:
                copy_from_dataframe(processor(output_path))
            except Exception as e:
                logger.error("Error in %s: %s", processor.__name__, e)

        try:
            index_data = fetch_index_list()
            if index_data:
                copy_from_dataframe(process_index_data(index_data))
        except Exception as e:
            logger.error("Error processing Index data: %s", e)

        delete_jainamxts_temp_data(output_path)

        if not _frames:
            return {"status": "error", "message": "No master-contract rows parsed", "count": 0}

        token_df = pd.concat(_frames, ignore_index=True)
        token_df = token_df.drop_duplicates(subset=["token", "exchange"], keep="last")
        data_dict = _nan_to_none(token_df.to_dict(orient="records"))

        async def _db_ops():
            engine, session_factory = _build_isolated_engine_and_session()
            try:
                async with session_factory() as session:
                    async with session.begin():
                        logger.info("Clearing symtoken table")
                        await session.execute(text("DELETE FROM symtoken"))
                        logger.info("Performing bulk insert of %d records", len(data_dict))
                        await session.execute(
                            text(
                                "INSERT INTO symtoken (symbol, brsymbol, name, exchange, brexchange, "
                                "token, expiry, strike, lotsize, instrumenttype, tick_size) "
                                "VALUES (:symbol, :brsymbol, :name, :exchange, :brexchange, "
                                ":token, :expiry, :strike, :lotsize, :instrumenttype, :tick_size)"
                            ),
                            data_dict,
                        )
            finally:
                await engine.dispose()

        asyncio.run(_db_ops())

        async def _refresh_caches():
            from backend.utils import symtoken_cache
            from backend.broker.upstox.mapping.order_data import _load_symbol_cache
            await symtoken_cache.warm_from_db()
            await _load_symbol_cache()

        asyncio.run(_refresh_caches())

        logger.info("Jainam master contract download completed (%d rows)", len(data_dict))
        return {
            "status": "success",
            "message": "Jainam XTS master contracts downloaded",
            "count": len(data_dict),
        }

    except Exception as e:
        logger.exception("Jainam master contract download failed")
        delete_jainamxts_temp_data(output_path)
        return {"status": "error", "message": str(e)}


async def search_symbols(symbol: str, exchange: str) -> list[dict]:
    tokens = [t for t in symbol.split() if t][:6]
    if not tokens:
        return []
    where_parts = ["exchange = :exchange"]
    params: dict = {"exchange": exchange, "prefix": f"{tokens[0]}%"}
    for i, tok in enumerate(tokens):
        key = f"t{i}"
        where_parts.append(
            f"(symbol ILIKE :{key} OR brsymbol ILIKE :{key} OR name ILIKE :{key})"
        )
        params[key] = f"%{tok}%"
    sql = (
        "SELECT symbol, brsymbol, name, exchange, brexchange, token, "
        "expiry, strike, lotsize, instrumenttype, tick_size "
        "FROM symtoken WHERE " + " AND ".join(where_parts) + " "
        "ORDER BY "
        "  CASE WHEN symbol ILIKE :prefix THEN 0 ELSE 1 END, "
        "  length(symbol), symbol "
        "LIMIT 50"
    )
    from backend.database import async_session
    async with async_session() as session:
        result = await session.execute(text(sql), params)
        return [
            {
                "symbol": r[0], "brsymbol": r[1], "name": r[2], "exchange": r[3],
                "brexchange": r[4], "token": r[5], "expiry": r[6], "strike": r[7],
                "lotsize": r[8], "instrumenttype": r[9], "tick_size": r[10],
            }
            for r in result.fetchall()
        ]

