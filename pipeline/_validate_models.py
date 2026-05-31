# =============================================================================
# pipeline/_validate_models.py — Model Doğrulama ve Rapor Üretici
# =============================================================================
# GÖREV   : analiz_pipeline.py yeniden çalıştırmak zorunda kalmadan mevcut
#           .pkl dosyalarından model metriklerini üretir ve karşılaştırır.
#
# ÇALIŞMA : python pipeline/_validate_models.py
#
# GEREKSİNİM: pipeline/ içinde şu dosyalar mevcut olmalı:
#   best_model_xgb.pkl, label_encoder.pkl, feature_columns.pkl,
#   influencer_summary_checkpoint.pkl
#
# ÇIKTILAR (docs/model_reports/):
#   confusion_matrices.png, feature_importance.png, model_comparison.png
#   model_validation_report.txt
# =============================================================================
import pickle, warnings, numpy as np, pandas as pd, joblib, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    confusion_matrix, ConfusionMatrixDisplay, classification_report,
)
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

PIPELINE_DIR = Path(__file__).parent
ROOT_DIR     = PIPELINE_DIR.parent
REPORTS_DIR  = ROOT_DIR / "docs" / "model_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Modelleri ve checkpoint'i yukle ─────────────────────────────────────────
xgb_model    = joblib.load(PIPELINE_DIR / "best_model_xgb.pkl")
le           = joblib.load(PIPELINE_DIR / "label_encoder.pkl")
feature_cols = joblib.load(PIPELINE_DIR / "feature_columns.pkl")

ckpt_candidates = [
    PIPELINE_DIR / "influencer_summary_checkpoint_safe.pkl",
    PIPELINE_DIR / "influencer_summary_checkpoint.pkl",
]
ckpt_path = next((p for p in ckpt_candidates if p.exists()), ckpt_candidates[-1])
with open(ckpt_path, "rb") as f:
    inf_sum = pickle.load(f)

# ── Model veri setini yeniden olustur ────────────────────────────────────────
CAMPAIGN_COLUMNS = {c.replace("sim_", ""): c for c in inf_sum.columns if c.startswith("sim_")}
rows = []
for _, inf in inf_sum.iterrows():
    for cname, scol in CAMPAIGN_COLUMNS.items():
        sfs = inf[scol]; nfs = inf["NFS"]; pr = inf["positive_ratio"]
        if sfs > 0.35 and nfs > 25 and pr > 60:
            label = "uygun"
        elif sfs < 0.20 or nfs < 15 or pr < 45:
            label = "uygun_degil"
        else:
            label = "orta"
        rows.append({
            "influencer_name": inf["influencer_name"], "campaign": cname,
            "category": inf["category"], "account_type": inf["account_type"],
            "engagement_rate": inf["engagement_rate"],
            "posts_per_month": inf["posts_per_month"], "NFS": nfs, "SFS": sfs,
            "positive_ratio": pr, "negative_ratio": inf["negative_ratio"],
            "avg_sentiment_score": inf["avg_sentiment_score"],
            "positive_comment_ratio": inf.get("positive_comment_ratio", 50.0),
            "negative_comment_ratio": inf.get("negative_comment_ratio", 20.0),
            "neutral_comment_ratio": inf.get("neutral_comment_ratio", 30.0),
            "avg_comment_sentiment": inf.get("avg_comment_sentiment", 0.5),
            "comment_count": inf.get("comment_count", 0),
            "label": label,
        })

df_model = pd.DataFrame(rows)
df_enc   = pd.get_dummies(df_model, columns=["category", "account_type", "campaign"])
X = df_enc.drop(columns=["influencer_name", "label"])
X = X.reindex(columns=feature_cols, fill_value=0)
y = df_enc["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

y_train_enc = le.transform(y_train)
y_test_enc  = le.transform(y_test)
y_enc       = le.transform(y)

# ── Tahminler ────────────────────────────────────────────────────────────────
y_pred_xgb = le.inverse_transform(xgb_model.predict(X_test))

lgbm = LGBMClassifier(n_estimators=100, learning_rate=0.1,
                       class_weight="balanced", random_state=42, verbose=-1)
lgbm.fit(X_train, y_train)
y_pred_lgbm = lgbm.predict(X_test)

rf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
rf.fit(X_train, y_train)
y_pred_rf = rf.predict(X_test)

class_names = sorted(y_test.unique())

# ════════════════════════════════════════════════════════════════════════════
# EKRANA YAZDIR
# ════════════════════════════════════════════════════════════════════════════

SEP = "=" * 60

print(SEP)
print("MODEL KARSILASTIRMASI (Test Seti)")
print(SEP)
print(f"{'Model':15s} {'Accuracy':>9} {'F1 (W)':>9} {'Precision':>10} {'Recall':>8}")
print("-" * 55)
models = {
    "XGBoost"     : (y_test.values, y_pred_xgb),
    "LightGBM"    : (y_test.values, y_pred_lgbm),
    "RandomForest": (y_test.values, y_pred_rf),
}
perf = {}
for name, (yt, yp) in models.items():
    acc  = accuracy_score(yt, yp)
    f1   = f1_score(yt, yp, average="weighted")
    prec = precision_score(yt, yp, average="weighted", zero_division=0)
    rec  = recall_score(yt, yp, average="weighted", zero_division=0)
    perf[name] = dict(Accuracy=acc, F1=f1, Precision=prec, Recall=rec)
    print(f"{name:15s} {acc:9.3f} {f1:9.3f} {prec:10.3f} {rec:8.3f}")

print()
print(SEP)
print("OVERFITTING ANALIZI (Train vs Test Accuracy)")
print(SEP)
print(f"{'Model':15s} {'Train':>8} {'Test':>8} {'Fark':>8}  Durum")
print("-" * 55)
overfit = [
    ("XGBoost",
     accuracy_score(y_train, le.inverse_transform(xgb_model.predict(X_train))),
     accuracy_score(y_test, y_pred_xgb)),
    ("LightGBM",
     accuracy_score(y_train, lgbm.predict(X_train)),
     accuracy_score(y_test, y_pred_lgbm)),
    ("RandomForest",
     accuracy_score(y_train, rf.predict(X_train)),
     accuracy_score(y_test, y_pred_rf)),
]
for name, tr, te in overfit:
    gap  = tr - te
    flag = "OVERFITTING" if gap > 0.10 else "OK"
    print(f"{name:15s} {tr:8.3f} {te:8.3f} {gap:8.3f}  {flag}")

print()
print(SEP)
print("5-FOLD CROSS VALIDATION (F1 Weighted)")
print(SEP)
cv_res = {}
for name, model, labels in [
    ("XGBoost",      xgb_model, y_enc),
    ("LightGBM",     lgbm,      y),
    ("RandomForest", rf,        y),
]:
    cv = cross_val_score(model, X, labels, cv=5, scoring="f1_weighted")
    cv_res[name] = cv
    print(f"{name:15s}: {cv.mean():.3f} +/- {cv.std():.3f}")

print()
print(SEP)
print("SINIFLANDIRMA RAPORU — XGBoost")
print(SEP)
print(classification_report(y_test.values, y_pred_xgb, zero_division=0))

# ════════════════════════════════════════════════════════════════════════════
# GRAFIK 1 — CONFUSION MATRIX
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle("Confusion Matrix Karsilastirmasi", fontsize=13, fontweight="bold")
for ax, (name, (yt, yp)) in zip(axes, models.items()):
    cm   = confusion_matrix(yt, yp, labels=class_names)
    disp = ConfusionMatrixDisplay(cm, display_labels=class_names)
    disp.plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"{name}  Acc={accuracy_score(yt,yp):.3f}", fontsize=10)
    ax.tick_params(axis="x", rotation=15)
plt.tight_layout()
out = REPORTS_DIR / "confusion_matrices.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Kaydedildi: {out}")

# ════════════════════════════════════════════════════════════════════════════
# GRAFIK 2 — FEATURE IMPORTANCE
# ════════════════════════════════════════════════════════════════════════════
feat_imp = pd.Series(xgb_model.feature_importances_, index=X.columns).nlargest(15).sort_values()
fig, ax = plt.subplots(figsize=(9, 6))
ax.barh(feat_imp.index, feat_imp.values, color="#6ee7b7", edgecolor="none")
ax.set_title("XGBoost — En Onemli 15 Ozellik", fontsize=12, fontweight="bold")
ax.spines[["top", "right", "left"]].set_visible(False)
ax.tick_params(axis="y", labelsize=9)
for i, (val, name) in enumerate(zip(feat_imp.values, feat_imp.index)):
    ax.text(val + 0.001, i, f"{val:.3f}", va="center", fontsize=8)
plt.tight_layout()
out = REPORTS_DIR / "feature_importance.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Kaydedildi: {out}")

# ════════════════════════════════════════════════════════════════════════════
# GRAFIK 3 — MODEL KARSILASTIRMA
# ════════════════════════════════════════════════════════════════════════════
metrics_list = ["Accuracy", "F1", "Precision", "Recall"]
model_list   = list(perf.keys())
colors       = ["#6ee7b7", "#818cf8", "#f472b6"]
x            = np.arange(len(metrics_list))
w            = 0.25

fig, ax = plt.subplots(figsize=(10, 5))
for i, (name, color) in enumerate(zip(model_list, colors)):
    vals  = [perf[name][m] for m in metrics_list]
    rects = ax.bar(x + i * w, vals, w, label=name, color=color, alpha=0.88)
    for r in rects:
        h = r.get_height()
        ax.text(r.get_x() + r.get_width()/2, h + 0.005,
                f"{h:.3f}", ha="center", va="bottom", fontsize=8)
ax.set_xticks(x + w)
ax.set_xticklabels(metrics_list, fontsize=11)
ax.set_ylim(0, 1.15)
ax.set_ylabel("Skor")
ax.set_title("Model Performans Karsilastirmasi", fontsize=12, fontweight="bold")
ax.legend(fontsize=10)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
out = REPORTS_DIR / "model_comparison.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Kaydedildi: {out}")

# ════════════════════════════════════════════════════════════════════════════
# YAZILI RAPOR
# ════════════════════════════════════════════════════════════════════════════
rpt_path = REPORTS_DIR / "model_validation_report.txt"
with open(rpt_path, "w", encoding="utf-8") as rpt:
    rpt.write("=" * 65 + "\n")
    rpt.write("FENOMEN-MARKA ESLESTIRME — MODEL DOGRULAMA RAPORU\n")
    rpt.write("TÜBİTAK 2209-A Projesi\n")
    rpt.write("=" * 65 + "\n\n")

    rpt.write("1. VERI SETI\n" + "-"*40 + "\n")
    rpt.write(f"  Toplam ornek  : {len(df_model)}\n")
    rpt.write(f"  Egitim seti   : {len(X_train)}\n")
    rpt.write(f"  Test seti     : {len(X_test)}\n")
    rpt.write(f"  Sinif sayisi  : {len(class_names)} ({', '.join(class_names)})\n")
    rpt.write("\n  Etiket dagilimi:\n")
    for lbl, cnt in df_model["label"].value_counts().items():
        rpt.write(f"    {lbl}: {cnt}\n")

    rpt.write("\n2. MODEL PERFORMANSI\n" + "-"*40 + "\n")
    rpt.write(f"  {'Model':15s} {'Accuracy':>9} {'F1':>7} {'Precision':>10} {'Recall':>8}\n")
    for name, p in perf.items():
        rpt.write(f"  {name:15s} {p['Accuracy']:9.3f} {p['F1']:7.3f} {p['Precision']:10.3f} {p['Recall']:8.3f}\n")

    rpt.write("\n3. OVERFITTING ANALIZI\n" + "-"*40 + "\n")
    for name, tr, te in overfit:
        gap = tr - te
        rpt.write(f"  {name:15s} Train={tr:.3f}  Test={te:.3f}  Fark={gap:.3f}  {'OVERFITTING' if gap>0.10 else 'OK'}\n")

    rpt.write("\n4. CROSS VALIDATION (5-Fold)\n" + "-"*40 + "\n")
    for name, cv in cv_res.items():
        rpt.write(f"  {name:15s}: {cv.mean():.3f} +/- {cv.std():.3f}\n")

    rpt.write("\n5. SINIFLANDIRMA RAPORU (XGBoost)\n" + "-"*40 + "\n")
    rpt.write(classification_report(y_test.values, y_pred_xgb, zero_division=0))

    rpt.write("\n6. FEATURE IMPORTANCE (Top 15)\n" + "-"*40 + "\n")
    for feat, imp in feat_imp.sort_values(ascending=False).items():
        rpt.write(f"  {feat:40s} {imp:.4f}\n")

print(f"Kaydedildi: {rpt_path}")
print("\nTAMAMLANDI — model_reports/ klasoru:")
for p in sorted(REPORTS_DIR.iterdir()):
    print(f"  {p.name:35s} {p.stat().st_size//1024:>4} KB")
