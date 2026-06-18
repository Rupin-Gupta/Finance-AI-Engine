-- P14: trained ML directional models — metadata + promotion flag (model bytes on disk volume).
CREATE TABLE IF NOT EXISTS ml_models (
    id            SERIAL PRIMARY KEY,
    version       TEXT NOT NULL UNIQUE,
    trained_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon       INT NOT NULL,
    threshold     NUMERIC(8,5) NOT NULL,
    n_samples     INT,
    n_features    INT,
    oos_auc       NUMERIC(8,5),
    oos_hit_rate  NUMERIC(8,5),
    oos_brier     NUMERIC(8,5),
    promoted      BOOLEAN NOT NULL DEFAULT FALSE,
    path          TEXT NOT NULL,
    feature_names TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_ml_models_promoted ON ml_models (promoted, trained_at DESC);
