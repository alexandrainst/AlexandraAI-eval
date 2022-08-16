"""All task configurations used in the project."""

from typing import Dict

from .config import Label, MetricConfig, TaskConfig


def get_all_task_configs() -> Dict[str, TaskConfig]:
    """Get a list of all the dataset tasks.

    Returns:
        dict:
            A mapping between names of dataset tasks and their configurations.
    """
    return {cfg.name: cfg for cfg in globals().values() if isinstance(cfg, TaskConfig)}


NER = TaskConfig(
    name="ner",
    dataset_name="dane",
    pretty_dataset_name="DaNE",
    huggingface_id="dane",
    supertask="token-classification",
    metrics=[
        MetricConfig(
            name="micro_f1",
            pretty_name="Micro-average F1-score",
            huggingface_id="seqeval",
            results_key="overall_f1",
        ),
        MetricConfig(
            name="micro_f1_no_misc",
            pretty_name="Micro-average F1-score without MISC tags",
            huggingface_id="seqeval",
            results_key="overall_f1",
        ),
    ],
    labels=[
        Label(
            name="O",
            synonyms=[],
        ),
        Label(
            name="B-LOC",
            synonyms=[
                "B-LOCATION",
                "B-PLACE",
                "B-GPELOC",
                "B-GPE_LOC",
                "B-GPE/LOC",
                "B-LOCGPE",
                "B-LOC_GPE",
                "B-LOC/GPE",
                "B-LOCORG",
                "B-LOC_ORG",
                "B-LOC/ORG",
                "B-ORGLOC",
                "B-ORG_LOC",
                "B-ORG/LOC",
                "B-LOCPRS",
                "B-LOC_PRS",
                "B-LOC/PRS",
                "B-PRSLOC",
                "B-PRS_LOC",
                "B-PRS/LOC",
            ],
        ),
        Label(
            name="I-LOC",
            synonyms=[
                "I-LOCATION",
                "I-PLACE",
                "I-GPELOC",
                "I-GPE_LOC",
                "I-GPE/LOC",
                "I-LOCGPE",
                "I-LOC_GPE",
                "I-LOC/GPE",
                "I-LOCORG",
                "I-LOC_ORG",
                "I-LOC/ORG",
                "I-ORGLOC",
                "I-ORG_LOC",
                "I-ORG/LOC",
                "I-LOCPRS",
                "I-LOC_PRS",
                "I-LOC/PRS",
                "I-PRSLOC",
                "I-PRS_LOC",
                "I-PRS/LOC",
            ],
        ),
        Label(
            name="B-ORG",
            synonyms=[
                "B-ORGANIZATION",
                "B-ORGANISATION",
                "B-INST",
                "B-GPEORG",
                "B-GPE_ORG",
                "B-GPE/ORG",
                "B-ORGGPE",
                "B-ORG_GPE",
                "B-ORG/GPE",
                "B-ORGPRS",
                "B-ORG_PRS",
                "B-ORG/PRS",
                "B-PRSORG",
                "B-PRS_ORG",
                "B-PRS/ORG",
                "B-OBJORG",
                "B-OBJ_ORG",
                "B-OBJ/ORG",
                "B-ORGOBJ",
                "B-ORG_OBJ",
                "B-ORG/OBJ",
            ],
        ),
        Label(
            name="I-ORG",
            synonyms=[
                "I-ORGANIZATION",
                "I-ORGANISATION",
                "I-INST",
                "I-GPEORG",
                "I-GPE_ORG",
                "I-GPE/ORG",
                "I-ORGGPE",
                "I-ORG_GPE",
                "I-ORG/GPE",
                "I-ORGPRS",
                "I-ORG_PRS",
                "I-ORG/PRS",
                "I-PRSORG",
                "I-PRS_ORG",
                "I-PRS/ORG",
                "I-OBJORG",
                "I-OBJ_ORG",
                "I-OBJ/ORG",
                "I-ORGOBJ",
                "I-ORG_OBJ",
                "I-ORG/OBJ",
            ],
        ),
        Label(
            name="B-PER",
            synonyms=["B-PERSON"],
        ),
        Label(
            name="I-PER",
            synonyms=["I-PERSON"],
        ),
        Label(
            name="B-MISC",
            synonyms=["B-MISCELLANEOUS"],
        ),
        Label(
            name="I-MISC",
            synonyms=["I-MISCELLANEOUS"],
        ),
    ],
    split_names={"train": "train", "test": "test", "val": "validation"},
)


SENT = TaskConfig(
    name="sent",
    dataset_name="angry-tweets",
    pretty_dataset_name="Angry Tweets",
    huggingface_id="DDSC/angry-tweets",
    supertask="text-classification",
    metrics=[
        MetricConfig(
            name="mcc",
            pretty_name="Matthew's Correlation Coefficient",
            huggingface_id="matthews_correlation",
            results_key="matthews_correlation",
        ),
        MetricConfig(
            name="macro_f1",
            pretty_name="Macro-average F1-score",
            huggingface_id="f1",
            results_key="f1",
            compute_kwargs=dict(average="macro"),
        ),
    ],
    labels=[
        Label(
            name="NEGATIVE",
            synonyms=["NEG", "NEGATIV", "LABEL_0"],
        ),
        Label(
            name="NEUTRAL",
            synonyms=["NEU", "LABEL_1"],
        ),
        Label(
            name="POSITIVE",
            synonyms=["POS", "POSITIV", "LABEL_2"],
        ),
    ],
    split_names={"train": "train", "test": "test", "val": None},
)
