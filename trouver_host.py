import psycopg2

for prefix in ["aws-0", "aws-1"]:
    for region in ["eu-west-3", "eu-central-1", "eu-west-1", "eu-west-2", "eu-north-1",
                   "us-east-1", "us-east-2", "us-west-1", "ap-southeast-1"]:
        host = f"{prefix}-{region}.pooler.supabase.com"
        try:
            psycopg2.connect(host=host, port=5432, dbname="postgres",
                             user="postgres.rztrzvfauvooicxfxihq",
                             password="IPSSI_Database", sslmode="require",
                             connect_timeout=5).close()
            print("HOST TROUVE :", host)
            raise SystemExit
        except psycopg2.OperationalError as e:
            print("X", host, "-", str(e).strip().splitlines()[-1][:80])