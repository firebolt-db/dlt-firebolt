"""Tests for firebolt_dest (no Firebolt connection required)."""

from firebolt_dest.copy_sql import gen_firebolt_copy_sql, s3_url_to_copy_pattern


def test_s3_url_to_copy_pattern() -> None:
    url = "s3://my-bucket/dlt-landing/dlt/staging/hubspot/file.parquet"
    assert (
        s3_url_to_copy_pattern(url, "dlt-landing")
        == "dlt/staging/hubspot/file.parquet"
    )


def test_gen_firebolt_copy_sql() -> None:
    sql = gen_firebolt_copy_sql(
        "demo_hubspot_contacts",
        location_name="firebolt_s3",
        pattern="dlt/staging/*.parquet",
        file_format="parquet",
    )
    assert "COPY INTO demo_hubspot_contacts" in sql
    assert "FROM firebolt_s3" in sql
    assert "TYPE = PARQUET" in sql
    assert "dlt/staging/*.parquet" in sql
