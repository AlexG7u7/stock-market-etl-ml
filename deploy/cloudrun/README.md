# Job diario en Cloud Run

Tres jobs de Cloud Run, zona `America/Mexico_City`, proyecto `domesticospro`.
Postgres es Cloud SQL `domesticospro:us-central1:domesticos-pg`, base `mercado`, esquema `lab`.
La imagen no lleva `.env` ni `data/market`: los secretos entran como variables del job y los precios del día salen de yfinance si no hay parquet local.

El script es `scripts/gcp_daily_job.py` (`--mode ingest|decide|score`).

| Horario | Qué corre | Job |
| --- | --- | --- |
| lun–vie 18:30 | precios del día + noticias | `mercado-daily-ingest` |
| sáb y dom 18:30 | el mismo job; el script solo mete noticias | `mercado-daily-ingest` |
| lun–vie 19:15 | plan de entrada del siguiente día hábil | `mercado-daily-decide` |
| lun–vie 20:00 | score de planes cuyo horizonte ya cumplió | `mercado-daily-score` |

Cloud Scheduler ya está activado en `domesticospro`. Los comandos de jobs de abajo todavía no se han ejecutado.

## Secretos

No van en el repo ni en esta página.

- `mercado-database-url`: URL de Postgres de la base `mercado` por el socket `/cloudsql/domesticospro:us-central1:domesticos-pg`. El job la recibe como `LAB_DATABASE_URL` (`src/db/lab_store.py`). Si solo existe `DATABASE_URL`, el script la copia a ese nombre.
- `xai-api-key`: solo el job `decide`. Sin `XAI_API_KEY` el script no llama al LLM y arma el plan con el libro y el ranking.

## Build y jobs

Desde la raíz del repo. `.dockerignore` deja fuera `.env` y los parquet.

```bash
gcloud config set project domesticospro

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  --project=domesticospro

gcloud artifacts repositories create mercado \
  --project=domesticospro \
  --repository-format=docker \
  --location=us-central1 \
  --description="Imagen del job diario de mercado"

gcloud iam service-accounts create mercado-daily \
  --project=domesticospro \
  --display-name="Job diario mercado"

gcloud projects add-iam-policy-binding domesticospro \
  --member="serviceAccount:mercado-daily@domesticospro.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud builds submit \
  --project=domesticospro \
  --region=us-central1 \
  --tag=us-central1-docker.pkg.dev/domesticospro/mercado/daily-job:latest \
  --file=deploy/cloudrun/Dockerfile \
  .

gcloud run jobs create mercado-daily-ingest \
  --project=domesticospro \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/domesticospro/mercado/daily-job:latest \
  --service-account=mercado-daily@domesticospro.iam.gserviceaccount.com \
  --set-cloudsql-instances=domesticospro:us-central1:domesticos-pg \
  --set-secrets=LAB_DATABASE_URL=mercado-database-url:latest \
  --set-env-vars=DB_NAME=mercado,DB_SCHEMA=lab \
  --command=python \
  --args=scripts/gcp_daily_job.py,--mode,ingest \
  --max-retries=1 \
  --task-timeout=3600 \
  --memory=4Gi \
  --cpu=2

gcloud run jobs create mercado-daily-decide \
  --project=domesticospro \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/domesticospro/mercado/daily-job:latest \
  --service-account=mercado-daily@domesticospro.iam.gserviceaccount.com \
  --set-cloudsql-instances=domesticospro:us-central1:domesticos-pg \
  --set-secrets=LAB_DATABASE_URL=mercado-database-url:latest,XAI_API_KEY=xai-api-key:latest \
  --set-env-vars=DB_NAME=mercado,DB_SCHEMA=lab \
  --command=python \
  --args=scripts/gcp_daily_job.py,--mode,decide \
  --max-retries=1 \
  --task-timeout=1800 \
  --memory=2Gi \
  --cpu=1

gcloud run jobs create mercado-daily-score \
  --project=domesticospro \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/domesticospro/mercado/daily-job:latest \
  --service-account=mercado-daily@domesticospro.iam.gserviceaccount.com \
  --set-cloudsql-instances=domesticospro:us-central1:domesticos-pg \
  --set-secrets=LAB_DATABASE_URL=mercado-database-url:latest \
  --set-env-vars=DB_NAME=mercado,DB_SCHEMA=lab \
  --command=python \
  --args=scripts/gcp_daily_job.py,--mode,score \
  --max-retries=1 \
  --task-timeout=1800 \
  --memory=2Gi \
  --cpu=1
```

Si el job ya existe, el mismo comando con `gcloud run jobs update` y los mismos flags.

## Cloud Scheduler

Hay que activar la API antes de crear los disparos:

```bash
gcloud services enable cloudscheduler.googleapis.com --project=domesticospro
```

```bash
gcloud iam service-accounts create mercado-scheduler \
  --project=domesticospro \
  --display-name="Scheduler del job diario"

for job in mercado-daily-ingest mercado-daily-decide mercado-daily-score; do
  gcloud run jobs add-iam-policy-binding "$job" \
    --project=domesticospro \
    --region=us-central1 \
    --member="serviceAccount:mercado-scheduler@domesticospro.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
done

gcloud scheduler jobs create http mercado-ingest-lv \
  --project=domesticospro \
  --location=us-central1 \
  --schedule="30 18 * * 1-5" \
  --time-zone="America/Mexico_City" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/domesticospro/jobs/mercado-daily-ingest:run" \
  --http-method=POST \
  --message-body="{}" \
  --oauth-service-account-email=mercado-scheduler@domesticospro.iam.gserviceaccount.com

gcloud scheduler jobs create http mercado-ingest-weekend \
  --project=domesticospro \
  --location=us-central1 \
  --schedule="30 18 * * 0,6" \
  --time-zone="America/Mexico_City" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/domesticospro/jobs/mercado-daily-ingest:run" \
  --http-method=POST \
  --message-body="{}" \
  --oauth-service-account-email=mercado-scheduler@domesticospro.iam.gserviceaccount.com

gcloud scheduler jobs create http mercado-decide-lv \
  --project=domesticospro \
  --location=us-central1 \
  --schedule="15 19 * * 1-5" \
  --time-zone="America/Mexico_City" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/domesticospro/jobs/mercado-daily-decide:run" \
  --http-method=POST \
  --message-body="{}" \
  --oauth-service-account-email=mercado-scheduler@domesticospro.iam.gserviceaccount.com

gcloud scheduler jobs create http mercado-score-lv \
  --project=domesticospro \
  --location=us-central1 \
  --schedule="0 20 * * 1-5" \
  --time-zone="America/Mexico_City" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/domesticospro/jobs/mercado-daily-score:run" \
  --http-method=POST \
  --message-body="{}" \
  --oauth-service-account-email=mercado-scheduler@domesticospro.iam.gserviceaccount.com
```

`0,6` es domingo y sábado. El score no elige el plan a mano: `score` descarta los que todavía no cumplen `enter_on` + `horizon_days` hábiles.

## Contrato con lab_store

`src/db/lab_store.py` habla con `sql/03_lab_schema.sql`. `psycopg[binary]` está en `requirements.txt`. El esquema `lab` ya existe en la base `mercado`.

- `upsert_prices` → `lab.price_daily`
- `insert_news` → `lab.news_daily` (título, fuente, sentimiento, url del día)
- `insert_decision(..., plans=)` → `lab.decision` y `lab.entry_plan` (`horizon` como `20d`)
- score lee planes sin fila en `lab.outcome` y escribe `realized_return`, `hit_stop` y una nota con entrada, close y stop

Sin URL imprime el plan o el scorecard y deja copia en `data/lab/`.
