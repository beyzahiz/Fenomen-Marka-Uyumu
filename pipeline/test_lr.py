import pickle, warnings, joblib
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score, f1_score, precision_score, recall_score
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline as SkPipeline

PIPELINE_DIR = Path(__file__).parent

# Checkpoint yukle
ckpt_candidates = [
    PIPELINE_DIR / "influencer_summary_checkpoint_safe.pkl",
    PIPELINE_DIR / "influencer_summary_checkpoint.pkl",
]
ckpt_path = next((p for p in ckpt_candidates if p.exists()), ckpt_candidates[-1])
with open(ckpt_path, "rb") as f:
    inf_sum = pickle.load(f)

le           = joblib.load(PIPELINE_DIR / "label_encoder.pkl")
feature_cols = joblib.load(PIPELINE_DIR / "feature_columns.pkl")

# Kampanya kolonlarini bul
sim_cols = [c for c in inf_sum.columns if c.startswith("sim_")]
CAMPAIGN_COLUMNS = {c.replace("sim_", ""): c for c in sim_cols}

# Model veri setini olustur
rows = []
for _, inf in inf_sum.iterrows():
    for cname, scol in CAMPAIGN_COLUMNS.items():
        if scol not in inf_sum.columns:
            continue
        sfs = inf[scol]; nfs = inf["NFS"]; pr = inf["positive_ratio"]
        if sfs > 0.35 and nfs > 25 and pr > 60:
            label = "uygun"
        elif sfs < 0.20 or nfs < 15 or pr < 45:
            label = "uygun_degil"
        else:
            label = "orta"
        rows.append({
            "influencer_name"     : inf["influencer_name"],
            "campaign"            : cname,
            "category"            : inf.get("category", ""),
            "account_type"        : inf.get("account_type", ""),
            "engagement_rate"     : inf.get("engagement_rate", 0),
            "posts_per_month"     : inf.get("posts_per_month", 0),
            "NFS"                 : nfs,
            "SFS"                 : sfs,
            "positive_ratio"      : pr,
            "negative_ratio"      : inf.get("negative_ratio", 20),
            "avg_sentiment_score" : inf.get("avg_sentiment_score", 0.5),
            "positive_comment_ratio": inf.get("positive_comment_ratio", 50.0),
            "negative_comment_ratio": inf.get("negative_comment_ratio", 20.0),
            "neutral_comment_ratio" : inf.get("neutral_comment_ratio", 30.0),
            "avg_comment_sentiment" : inf.get("avg_comment_sentiment", 0.5),
            "comment_count"         : inf.get("comment_count", 0),
            "label"               : label,
        })

df_model = pd.DataFrame(rows)
df_enc   = pd.get_dummies(df_model, columns=["category", "account_type", "campaign"])
X = df_enc.drop(columns=["influencer_name", "label"])
X = X.reindex(columns=feature_cols, fill_value=0)
y = df_enc["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Logistic Regression egit
lr_pipeline = SkPipeline([
    ("scaler", StandardScaler()),
    ("lr", LogisticRegression(
        max_iter=1000, class_weight="balanced",
        solver="lbfgs", random_state=42,
    )),
])
lr_pipeline.fit(X_train, y_train)
y_pred = lr_pipeline.predict(X_test)

# Sonuclar
print("=" * 55)
print("LOGISTIC REGRESSION — TEST SONUCLARI")
print("=" * 55)
print(f"Accuracy  : {accuracy_score(y_test, y_pred):.4f}")
print(f"F1 (W)    : {f1_score(y_test, y_pred, average='weighted'):.4f}")
print(f"Precision : {precision_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
print(f"Recall    : {recall_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")

train_acc = accuracy_score(y_train, lr_pipeline.predict(X_train))
test_acc  = accuracy_score(y_test, y_pred)
print(f"\nTrain Acc : {train_acc:.4f}")
print(f"Test Acc  : {test_acc:.4f}")
print(f"Fark      : {train_acc - test_acc:.4f}  {'[OVERFITTING]' if train_acc - test_acc > 0.10 else '[OK]'}")

cv = cross_val_score(lr_pipeline, X, y, cv=5, scoring="f1_weighted")
print(f"\n5-Fold CV F1: {cv.mean():.3f} +/- {cv.std():.3f}")
print(f"Fold skorlari: {[round(v,3) for v in cv]}")

print("\n" + classification_report(y_test, y_pred, zero_division=0))

# Kaydet
joblib.dump(lr_pipeline, PIPELINE_DIR / "best_model_lr.pkl")
print("best_model_lr.pkl kaydedildi.")
