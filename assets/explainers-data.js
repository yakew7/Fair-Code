window.FAIR_CODE_EXPLAINERS = [
  {
    "slug": "proxy-variables",
    "title": "Proxy Variables",
    "subtitle": "Why removing race alone does not remove bias.",
    "summary": "Learn how correlated features like zip code, custody status, and employment history can smuggle protected attributes back into a model.",
    "tags": [
      "detection",
      "data",
      "explainability"
    ]
  },
  {
    "slug": "equalized-odds",
    "title": "Equalized Odds",
    "subtitle": "A fairness metric that checks error rates, not just accuracy.",
    "summary": "See how equalized odds compares true positive and false positive rates across groups and why that matters in high-stakes systems.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "sampling-bias",
    "title": "Sampling Bias",
    "subtitle": "When your dataset does not reflect the world it claims to describe.",
    "summary": "Understand how under-sampling, over-sampling, and skewed collection pipelines can distort what a model learns.",
    "tags": [
      "data",
      "case-study"
    ]
  },
  {
    "slug": "shap-values",
    "title": "SHAP Values",
    "subtitle": "Explain model decisions feature by feature.",
    "summary": "Use SHAP to trace which inputs pushed a prediction up or down, and where explanation can still be misleading.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "disparate-impact",
    "title": "Disparate Impact",
    "subtitle": "When outcomes differ even without explicit intent.",
    "summary": "Measure whether a model or policy produces unequal results across groups, even when the protected attribute is hidden.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "disparate-treatment",
    "title": "Disparate Treatment",
    "subtitle": "Direct discrimination instead of proxy discrimination.",
    "summary": "Look at the difference between explicitly using protected attributes and indirectly encoding them through features.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "fairness-metric-conflicts",
    "title": "Fairness Metric Conflicts",
    "subtitle": "Why one fairness definition often breaks another.",
    "summary": "Understand the trade-offs between demographic parity, calibration, and equalized odds before choosing a metric.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "calibration",
    "title": "Calibration",
    "subtitle": "When a model score actually means what it says.",
    "summary": "Check whether predicted probabilities match real-world frequencies across groups and where calibration can still fail.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "demographic-parity",
    "title": "Demographic Parity",
    "subtitle": "Equal positive rates across groups.",
    "summary": "Learn when demographic parity is useful, where it breaks down, and why it can conflict with other fairness goals.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "feedback-loop-bias",
    "title": "Feedback Loop Bias",
    "subtitle": "Bias that gets stronger after deployment.",
    "summary": "See how model outputs feed back into future data and amplify unfairness over time.",
    "tags": [
      "data",
      "case-study"
    ]
  },
  {
    "slug": "label-bias",
    "title": "Label Bias",
    "subtitle": "When the target itself is already skewed.",
    "summary": "Explore how historical decisions, biased raters, and unequal reporting can corrupt your labels before training even starts.",
    "tags": [
      "data"
    ]
  },
  {
    "slug": "individual-fairness",
    "title": "Individual Fairness",
    "subtitle": "Similar people should get similar outcomes.",
    "summary": "Understand the promise and difficulty of fairness definitions that focus on person-by-person consistency.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "counterfactual-fairness",
    "title": "Counterfactual Fairness",
    "subtitle": "Would the outcome change if identity changed?",
    "summary": "Use counterfactual reasoning to ask whether a model would behave differently under a hypothetical protected attribute.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "neural-networks",
    "title": "Neural Networks",
    "subtitle": "How complex models can hide simple bias.",
    "summary": "Break down how layered models learn patterns, why they are hard to inspect, and why fairness audits matter even more.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "ai-hallucinations",
    "title": "AI Hallucinations",
    "subtitle": "Confident outputs that are still wrong.",
    "summary": "See how hallucinations interact with bias, why they are dangerous, and how to spot them in practice.",
    "tags": [
      "explainability",
      "case-study"
    ]
  },
  {
    "slug": "reinforcement-learning",
    "title": "Reinforcement Learning",
    "subtitle": "When reward signals shape real-world policy.",
    "summary": "Learn how RL-style systems can reinforce unfair incentives in recommendation, pricing, and risk scoring.",
    "tags": [
      "explainability",
      "data",
      "case-study"
    ]
  },
  {
    "slug": "proxy-entanglement",
    "title": "Proxy Entanglement",
    "subtitle": "When proxies form clusters instead of single features.",
    "summary": "Explore how correlated proxy bundles can keep bias alive even after individual features are removed.",
    "tags": [
      "detection",
      "data",
      "explainability"
    ]
  },
  {
    "slug": "ml-bias",
    "title": "What Is Machine Learning Bias?",
    "subtitle": "Four entry points. One pipeline. Measurable everywhere.",
    "summary": "Understand how bias enters AI systems through training data, labels, proxy variables, and feedback loops - with detection code and real examples from every audit in this repo.",
    "tags": [
      "detection",
      "data",
      "explainability"
    ]
  },
  {
    "slug": "data-leakage",
    "title": "What Is Data Leakage?",
    "subtitle": "When the model has already seen the answer sheet.",
    "summary": "Data leakage contaminates a model's training signal with information unavailable at deployment, producing evaluation scores that overstate real-world performance. Learn to identify target leakage and train-test contamination - and detect both before they ship.",
    "tags": [
      "data",
      "detection"
    ]
  },
  {
    "slug": "how-ai-detects-patterns",
    "title": "How AI Detects Patterns",
    "subtitle": "A model can't tell a cause from a proxy",
    "summary": "Learn how a Random Forest finds patterns through splits, tree aggregation, and feature importance. See why a high importance score means reliance, not justification.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "distribution-shift",
    "title": "Distribution Shift",
    "subtitle": "A fairness audit is only valid for the data it was run on",
    "summary": "Learn why a model that passes a bias audit at launch can drift back into bias as the population it serves changes over time. Covers covariate shift, label shift, and concept drift, with detection code for monitoring both.",
    "tags": [
      "data",
      "detection"
    ]
  },
  {
    "slug": "ai-objectivity-myth",
    "title": "The Biggest Myth About AI Objectivity",
    "subtitle": "\"It's just math\" is not a defense",
    "summary": "Learn why statistical models trained on biased history reproduce that bias regardless of intent. See how COMPAS's \"neutral\" risk score hid an 86.77% fairness gap until the right proxies were found.",
    "tags": [
      "data",
      "explainability"
    ]
  },
  {
    "slug": "confounding-variable",
    "title": "Confounding Variable",
    "subtitle": "When a hidden cause makes two things look connected.",
    "summary": "Learn how a third variable that independently causes both a feature and an outcome creates spurious correlations that survive protected-attribute removal. See why COMPAS stayed biased after race was dropped - until the confounder was removed too.",
    "tags": [
      "detection",
      "data"
    ]
  },
  {
    "slug": "predictive-parity",
    "title": "Predictive Parity",
    "subtitle": "Equally trustworthy is not the same as equally fair",
    "summary": "Learn why Positive Predictive Value equal across groups is a real fairness property, and why the 2016 ProPublica vs Northpointe COMPAS dispute shows it can hold while one group absorbs a much higher false-positive rate.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "false-positives-vs-false-negatives",
    "title": "False Positives vs. False Negatives in Medical Risk Models",
    "subtitle": "When a missed high-risk flag costs more than a false alarm",
    "summary": "Learn why a single accuracy or AUC number can hide two very different kinds of mistakes, and why a missed diagnosis and a false alarm are almost never equally costly. See how one global decision threshold can produce equal overall accuracy while still leaving very different false negative rates across demographic groups.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "supervised-learning",
    "title": "What Is Supervised Learning?",
    "subtitle": "Teaching a model to reproduce exactly what it was shown",
    "summary": "See how a model turns labeled examples into a decision rule by walking through the AI Fair Recruitment audit's train/test split and fit step directly. Includes detection code that compares the gap in a dataset's labels against the gap in a trained model's own predictions.",
    "tags": [
      "explainability",
      "data"
    ]
  },
  {
    "slug": "unsupervised-learning",
    "title": "What Is Unsupervised Learning?",
    "subtitle": "It found the split on its own, because the split was already in the data",
    "summary": "See how k-means clustering on the Benefits Denial dataset recovers a strong sex split (89.3% male in one cluster) and a real race split without sex, race, or national origin ever being part of the feature set. Includes detection code that clusters on non-protected features, then checks the result for demographic skew.",
    "tags": [
      "detection",
      "explainability",
      "case-study"
    ]
  },
  {
    "slug": "model-drift",
    "title": "What Is Model Drift?",
    "subtitle": "A fairness audit is a photograph of a moving room",
    "summary": "Learn why a fairness gap measured once at launch is not guaranteed to hold months later, and how rolling-window monitoring catches the drift a single audit snapshot misses. Re-measures the German Credit Lending age gap across five sequential windows (4.3%-15.1%) with PSI and a Page-Hinkley change-point test as detection code.",
    "tags": [
      "detection",
      "data"
    ]
  },
  {
    "slug": "selection-bias",
    "title": "What Is Selection Bias?",
    "subtitle": "A dataset does not remember the people who were turned away before it was collected.",
    "summary": "Learn why the process that decides whether someone enters a dataset at all can bias a model before any protected attribute or proxy is even considered. See why the German Credit Lending dataset's 700/300 good/bad split contains zero rejected applicants, and why that reject-inference gap survives Audit 03's proxy-variable fix untouched. Includes a Berkson's-paradox simulation as detection code.",
    "tags": [
      "data",
      "detection"
    ]
  },
  {
    "slug": "automation-bias",
    "title": "What Is Automation Bias?",
    "subtitle": "When humans defer to algorithms, bias gets automated too.",
    "summary": "Understand why judges, recruiters, and clinicians follow AI scores even when they know the scores are biased - and how automation bias amplifies disparities beyond what the model alone produces. Includes detection code measuring disparity amplification in human-in-the-loop decisions, mitigation strategies, and the COMPAS courtroom case study.",
    "tags": [
      "detection",
      "metrics",
      "explainability"
    ]
  },
  {
    "slug": "roc-curve-auc",
    "title": "What Is a ROC Curve and AUC?",
    "subtitle": "Why one threshold-free score can look great and still be unfair.",
    "summary": "Learn what a ROC curve and its area (AUC) actually measure - the model's ability to rank cases by risk - and why that single headline number hides the two things fairness depends on: where you set the decision threshold, and whether ranking quality is equal across groups. See how COMPAS's ordinary 0.68 baseline AUC (frozen from paper/results-frozen) sat on top of a large racial false-positive gap. Includes detection code for per-group AUC and overlaid ROC curves.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "class-imbalance",
    "title": "What Is Class Imbalance?",
    "subtitle": "When a 99% accuracy score just means the model ignored the 1% that mattered.",
    "summary": "Learn why skewed positive/negative ratios wreck naive accuracy and disproportionately hurt minority subgroups, and how common fixes (oversampling, undersampling, SMOTE, class weights) can either help or introduce new bias.",
    "tags": [
      "data",
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "bias-variance-tradeoff",
    "title": "What Is the Bias-Variance Trade-off?",
    "subtitle": "Why an overfit model can memorize the majority and fail the minority.",
    "summary": "Learn the difference between statistical bias and societal bias, and see how the classic trade-off between underfitting and overfitting impacts fairness across demographic groups.",
    "tags": [
      "detection",
      "explainability",
      "data"
    ]
  },
  {
    "slug": "confusion-matrix",
    "title": "What Is a Confusion Matrix?",
    "subtitle": "The foundational building block behind most fairness metrics.",
    "summary": "Learn how a confusion matrix breaks down accuracy into true positives, true negatives, false positives, and false negatives, and why derived metrics like FPR and FNR are essential for detecting bias.",
    "tags": [
      "metrics",
      "explainability"
    ]
  },
  {
    "slug": "protected-attribute",
    "title": "What Is a Protected Attribute?",
    "subtitle": "Why removing race from a dataset does not remove the bias.",
    "summary": "Learn what a protected attribute is, how the law recognizes it, and why the \"fairness through unawareness\" approach fails by hiding the bias behind proxies.",
    "tags": [
      "data",
      "explainability",
      "detection"
    ]
  },
  {
    "slug": "accuracy-not-enough-healthcare-ai",
    "title": "Why Accuracy Is Not Enough in Healthcare AI",
    "subtitle": "A 95% accurate model can still miss the sickest patients in one group.",
    "summary": "Learn why a high accuracy number can hide a model that systematically fails the patients who matter most. Covers the accuracy paradox on rare clinical outcomes (a 'predict nothing' model scoring 97% while catching zero at-risk patients), why a single aggregate score masks per-group recall and false-negative gaps, and why in medicine a missed case and a false alarm are never equally costly. Anchored to the Healthcare Readmission audit and the Obermeyer et al. (2019) study, with per-group accuracy-vs-recall detection code.",
    "tags": [
      "metrics",
      "detection",
      "healthcare"
    ]
  },
  {
    "slug": "clinical-score-miscalibration",
    "title": "Miscalibration in Clinical Risk Scores Across Groups",
    "subtitle": "The same risk score can mean a different real-world risk depending on the patient's group.",
    "summary": "Learn why a clinical risk score that is well-calibrated on average can still be miscalibrated for a specific patient group, so identical scores carry different real-world stakes. Covers reliability diagrams, calibration slope and intercept per group, why a shared score can be calibrated to the wrong target (as in Obermeyer et al. 2019), and why small subgroups make high-risk calibration hardest to verify. Anchored to the Healthcare Readmission audit with per-group reliability and calibration-slope detection code.",
    "tags": [
      "metrics",
      "detection",
      "healthcare"
    ]
  },
  {
    "slug": "missing-data-bias-ehr",
    "title": "Missing Data as Bias in Electronic Health Records",
    "subtitle": "A patient with fewer recorded labs and visits is less-observed, not lower-risk.",
    "summary": "Learn how unequal access to care turns into unequal missingness in EHR data, and why a model reading a blank field as 'nothing notable happened' is actually reading 'this group is observed less.' Covers the MCAR/MAR/MNAR framework, why naive imputation and row-dropping both make access-driven missingness worse, and why a missingness indicator can become a new proxy for the protected attribute it was meant to work around. Anchored to real missingness rates computed directly from the Healthcare Readmission dataset (a 10.7-point payer-code gap by race), with detection code that flags MNAR candidates by group.",
    "tags": [
      "data",
      "detection",
      "healthcare"
    ]
  },
  {
    "slug": "medical-imaging-representation-gaps",
    "title": "Why Medical Imaging Models Fail on Underrepresented Groups",
    "subtitle": "A model trained mostly on one group's images has barely seen the others.",
    "summary": "Learn why dermatology, radiology, and retinal imaging models underperform on groups thin in the training data, and the more insidious failure mode of shortcut learning, where a model keys off a confounder like scanner type or hospital site instead of the pathology. Covers the difference between a representation gap and shortcut confounding, why internal validation cannot rule out either, and per-group AUC plus proxy-detection code. Anchored to two documented real-world cases: Zech et al. (2018)'s hospital-site shortcut in pneumonia detection and Larrazabal et al. (2020)'s sex-imbalance study in chest X-ray diagnosis.",
    "tags": [
      "data",
      "detection",
      "healthcare",
      "case-study"
    ]
  },
  {
    "slug": "obermeyer-cost-proxy",
    "title": "The Obermeyer Case: When Cost Becomes a Proxy for Health Need",
    "subtitle": "How predicting healthcare spending instead of illness systematically under-refers sicker Black patients.",
    "summary": "Explore the canonical case study of Obermeyer et al. (2019): why using healthcare cost as a target variable creates racial bias, how historical spending disparities corrupt algorithm predictions, and how to audit models for proxy label bias using the Healthcare Readmission audit.",
    "tags": [
      "data",
      "detection",
      "metrics",
      "healthcare",
      "case-study"
    ]
  },
  {
    "slug": "underdiagnosis-bias",
    "title": "Underdiagnosis Bias in Healthcare AI",
    "subtitle": "When the label itself is sicker for one group.",
    "summary": "Learn how historical gaps in diagnostic testing and healthcare access cause ground-truth labels to under-count active disease in underserved groups - training models to systematically under-flag those exact patients. Covers the gap between true disease state and recorded EHR labels, why standard audits fail to catch unobserved false negatives, and biomarker-to-label consistency detection code.",
    "tags": [
      "data",
      "detection",
      "metrics",
      "healthcare",
      "case-study"
    ]
  },
  {
    "slug": "race-correction-clinical-algorithms",
    "title": "Race Correction in Clinical Algorithms",
    "subtitle": "Why race-adjusted clinical formulas bake bias directly into the math.",
    "summary": "Learn how race coefficients in formulas like eGFR kidney function, spirometry lung reference values, and the VBAC calculator delay care for Black and minority patients, why removing them is complex, and how to detect explicit race multipliers in clinical code.",
    "tags": [
      "data",
      "detection",
      "metrics",
      "healthcare",
      "case-study"
    ]
  },
  {
    "slug": "reject-inference",
    "title": "What Is Reject Inference?",
    "subtitle": "Why models trained only on approved applicants miss the risk of everyone else.",
    "summary": "Learn how missing ground-truth outcomes for rejected applicants create sample selection bias in lending, hiring, and insurance models, and how correction techniques like IPW, parceling, and Heckman models attempt to fix it. Anchored to German Credit Lending with Python simulation and correction code.",
    "tags": [
      "data",
      "detection",
      "metrics"
    ]
  },
  {
    "slug": "base-rate-fallacy",
    "title": "What Is the Base Rate Fallacy?",
    "subtitle": "Why ignoring background prevalence makes screening tools mostly wrong - and drives fairness metric conflicts.",
    "summary": "Learn how ignoring base rates leads to high false-alarm rates in screening algorithms, and why differing base rates across demographic groups make predictive parity and equalized odds mathematically incompatible. Covers Bayes' Theorem, PPV under low prevalence, the Chouldechova trade-off identity, and COMPAS audit detection code.",
    "tags": [
      "metrics",
      "detection",
      "explainability"
    ]
  },
  {
    "slug": "precision-recall-curve",
    "title": "What Is a Precision-Recall Curve?",
    "subtitle": "Why ROC/AUC looks fine while precision collapses under class imbalance.",
    "summary": "Learn what a precision-recall curve and average precision (AP) measure, and why they're the honest picture under the heavy class imbalance most fairness audits live in - rare positives, skewed base rates - where ROC/AUC's own arithmetic stays lenient. Anchored to Healthcare Readmission's 11.2% base rate (frozen 88.7% accuracy, 0.62 AUC, but 0.039 F1), with per-group average-precision detection code.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "equal-opportunity",
    "title": "What Is Equal Opportunity (and How It Differs From Equalized Odds)?",
    "subtitle": "Passing the true-positive-rate check doesn't mean passing the false-positive-rate one.",
    "summary": "Learn why Equal Opportunity only requires an equal true positive rate across groups, and how that relaxation can hide a false-positive-rate gap that Equalized Odds would catch. Uses two real frozen results: COMPAS, where the two metrics coincide, and Tenant Screening, where they diverge.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "intersectional-bias",
    "title": "What Is Intersectional Bias?",
    "subtitle": "Checking one protected attribute at a time can hide harm concentrated at the intersection.",
    "summary": "Learn why a fairness gap can be larger at the intersection of two protected attributes than either attribute's own single-axis check would predict - a compounding effect Crenshaw (1989) named intersectionality. Anchored to Benefits Denial's real, frozen superadditive gap for sex x national origin, with crosstab detection code and a pointer to the Open Dataset Profiler's own intersectional representation check.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "accuracy-equality",
    "title": "What Is Accuracy Equality?",
    "subtitle": "Equal accuracy across groups can hide two completely different, offsetting error profiles.",
    "summary": "Learn why Accuracy Equality only checks overall accuracy, and how a small accuracy gap can sit right next to a huge Equalized Odds gap on the exact same model. Uses COMPAS's real frozen numbers: a 3.5-point accuracy gap next to a 92.6-point Equalized Odds gap, driven by the true-positive-rate difference.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "bootstrap-confidence-intervals",
    "title": "What Is a Bootstrap Confidence Interval (and a Permutation Test)?",
    "subtitle": "A fairness gap without an interval attached is a number, not a finding.",
    "summary": "Learn how bootstrap resampling estimates a confidence interval and a permutation test estimates a p-value for any fairness gap, and why both matter most on the small subgroups audits routinely hit. Contrasts two real frozen COMPAS results: a tight, clearly significant Equal Opportunity gap and a wide, inconclusive Predictive Parity gap measured from just 6 rows.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "mitigation-strategies",
    "title": "What Are Pre-, In-, and Post-Processing Fairness Mitigations?",
    "subtitle": "Where in the pipeline you intervene changes what a fairness fix can and can't do.",
    "summary": "Learn the three families of fairness intervention - pre-processing, in-processing, and post-processing - through this repo's own five-strategy benchmark ladder. Anchored to COMPAS's real frozen progression (85.5% to 17.2% to 11.5% to -1.4% to 2.3% demographic parity gap), showing the three approaches converge rather than compound.",
    "tags": [
      "metrics",
      "data"
    ]
  },
  {
    "slug": "fairness-through-unawareness",
    "title": "Why Fairness Through Unawareness Fails",
    "subtitle": "Removing the protected attribute doesn't remove what correlates with it.",
    "summary": "Learn why dropping a protected attribute from a model's inputs is not the fairness fix it appears to be, using Tenant Screening's real frozen result: removing race from the model increased the demographic parity gap from 6.0 to 10.5 points, rather than closing it.",
    "tags": [
      "data",
      "detection"
    ]
  },
  {
    "slug": "lime",
    "title": "What Is LIME?",
    "subtitle": "A local, approximate surrogate model - the other major way to explain one prediction.",
    "summary": "Learn how LIME perturbs an input, fits a simple local model around it, and reads the surrogate's coefficients as an explanation - and why that approximation is a real trade-off against SHAP's exact, game-theoretic guarantees. Uses the same COMPAS prediction SHAP Values explains, for direct comparison.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "counterfactual-explanation",
    "title": "What Is a Counterfactual Explanation? (And How It Differs From Counterfactual Fairness)",
    "subtitle": "One asks what changed the outcome. The other asks whether the outcome should have changed at all.",
    "summary": "Learn what a counterfactual explanation is - the smallest input change that flips one specific decision - and why it's a different concept from Counterfactual Fairness despite the shared name. Covers the basis for real adverse-action notices in lending, with a from-scratch nearest-counterfactual search over German Credit Lending.",
    "tags": [
      "explainability"
    ]
  },
  {
    "slug": "multiple-comparisons",
    "title": "What Is a Multiple-Comparisons Correction (Bonferroni, Holm, and False Discovery Rate)?",
    "subtitle": "Run enough p-values at 0.05 and some will read \"significant\" by chance alone.",
    "summary": "Learn what Bonferroni, Holm, and Benjamini-Hochberg false discovery rate corrections actually do to a batch of p-values, and why this repo's own benchmark harness - dozens of p-values per audit, 1,320 in total - needs one. Applies all three to COMPAS's real 90-p-value slice from paper/results-frozen/results_fairness.csv, verified against statsmodels, showing exactly which \"significant\" findings survive correction and which don't.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "fairness-accuracy-tradeoff",
    "title": "What Is the Fairness-Accuracy Trade-off?",
    "subtitle": "Closing a fairness gap is rarely free, and the cost isn't always the same size.",
    "summary": "Learn why fairness-mitigation strategies that shrink a demographic parity gap often also reduce model accuracy, using COMPAS's real frozen numbers across all five strategies (accuracy falling from 65.3% to as low as 53.9% as the demographic parity gap closes from 85.5% toward roughly zero) - and why the trade-off isn't a fixed, linear cost.",
    "tags": [
      "metrics",
      "data"
    ]
  },
  {
    "slug": "treatment-equality",
    "title": "What Is Treatment Equality?",
    "subtitle": "Equal error rates across groups can still hide opposite-skewed error types within each group.",
    "summary": "Learn why Treatment Equality checks the ratio of false negatives to false positives within each group, not the individual rates Equalized Odds already compares. Uses COMPAS's real (freshly computed, not frozen) confusion matrix: a 0.13 FN:FP ratio for African-American defendants against a 31.0 ratio for Caucasian defendants on the same baseline model.",
    "tags": [
      "metrics"
    ]
  },
  {
    "slug": "simpsons-paradox",
    "title": "What Is Simpson's Paradox in Fairness Audits?",
    "subtitle": "A gap that shows up in the aggregate can shrink, vanish, or reverse once you disaggregate.",
    "summary": "Learn why an aggregate fairness metric is a weighted average of within-stratum rates, so pooling groups of different sizes can manufacture or flip a disparity. Uses the Benefits Denial (Adult Census) audit: the aggregate sex income gap of +19.6 pp collapses to roughly +3 pp within marital-status strata and reverses to -0.9 pp inside the largest one.",
    "tags": [
      "metrics",
      "data",
      "detection"
    ]
  },
  {
    "slug": "conditional-demographic-parity",
    "title": "What Is Conditional Demographic Parity?",
    "subtitle": "Checking parity within strata of a chosen legitimate factor, not across the whole population.",
    "summary": "Learn how conditional demographic parity refines plain demographic parity by stratifying on an explicitly chosen legitimate factor, and why the choice of that factor decides the answer. Uses the Benefits Denial (Adult Census) audit: conditioning the +19.6 pp sex income gap on education leaves it at +18.4 pp, while conditioning on marital status removes about 84% of it.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "subgroup-fairness",
    "title": "What Is Subgroup Fairness (and Fairness Gerrymandering)?",
    "subtitle": "Passing a fairness check on every attribute separately is not the same as passing it on every combination.",
    "summary": "Learn how a model can satisfy a fairness metric on each protected attribute individually yet fail on an algorithmically-discoverable subgroup, and how a brute-force subgroup scan differs from this repo's fixed-pair --cross. Uses the Healthcare Readmission audit: the gender readmission gap is 0.19 pp overall but -5.15 pp inside the Asian patient subgroup.",
    "tags": [
      "metrics",
      "detection"
    ]
  },
  {
    "slug": "differential-privacy",
    "title": "What Is Differential Privacy (and Its Tension With Fairness)?",
    "subtitle": "The accuracy cost of a privacy guarantee falls hardest on underrepresented groups.",
    "summary": "Learn how DP-SGD's gradient clipping and noise addition disproportionately degrade accuracy for minority subgroups, so adding a privacy guarantee to a bias-mitigation pipeline is not free. Illustrative example from Bagdasaryan, Poursaeed and Shmatikov (NeurIPS 2019), plus a runnable DP-SGD noise-injection toy; this repo trains no DP model, so no frozen numbers are quoted.",
    "tags": [
      "data",
      "metrics"
    ]
  },
  {
    "slug": "maxmin-fairness",
    "title": "What Is Max-Min (Rawlsian) Fairness?",
    "subtitle": "Make the worst-off group's outcome as good as possible, even if the groups end up unequal.",
    "summary": "Learn how max-min (Rawlsian) fairness minimizes the maximum group-level loss instead of equalizing a rate across groups, and why a model can move toward it while still failing demographic parity. Worked on the Audit 03 German Credit data: an iterative group-reweighting loop cuts worst-group error from 29.1% to 27.9% and leaves the 12-point selection-rate gap almost untouched.",
    "tags": [
      "metrics"
    ]
  }
];
