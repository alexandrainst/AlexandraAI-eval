"""Class for question-answering tasks."""

from collections import defaultdict
from typing import List, Sequence, Tuple

import numpy as np
from datasets.arrow_dataset import Dataset
from transformers.data.data_collator import DataCollator, default_data_collator
from transformers.tokenization_utils_base import BatchEncoding, PreTrainedTokenizerBase

from .config import TaskConfig
from .exceptions import FrameworkCannotHandleTask
from .task import Task


class QuestionAnswering(Task):
    """Question answering task.

    Args:
        task_config (TaskConfig):
            The configuration of the task.
        evaluation_config (EvaluationConfig):
            The configuration of the evaluation.

    Attributes:
        task_config (TaskConfig):
            The configuration of the task.
        evaluation_config (EvaluationConfig):
            The configuration of the evaluation.
    """

    def _pytorch_preprocess_fn(
        self,
        examples: BatchEncoding,
        tokenizer: PreTrainedTokenizerBase,
        pytorch_model_config: dict,
        task_config: TaskConfig,
    ) -> BatchEncoding:
        return prepare_test_examples(
            examples=examples,
            tokenizer=tokenizer,
        )

    def _load_data_collator(self, tokenizer: PreTrainedTokenizerBase) -> DataCollator:
        return default_data_collator

    def _prepare_predictions_and_labels(
        self,
        predictions: Sequence,
        dataset: Dataset,
        prepared_dataset: Dataset,
        **kwargs,
    ) -> List[Tuple[list, list]]:

        # Extract the predictions and labels
        predictions = postprocess_predictions(
            predictions=predictions,
            dataset=dataset,
            prepared_dataset=prepared_dataset,
            cls_token_index=kwargs["cls_token_index"],
        )
        labels = postprocess_labels(dataset=dataset)

        # Package the predictions and labels into the standard format and return them
        return [(predictions, labels)]

    def _check_if_model_is_trained_for_task(self, model_predictions: list) -> bool:
        sample_preds = model_predictions[0]
        elements_are_pairs = len(sample_preds[0]) == 2
        leaves_are_floats = isinstance(sample_preds[0][0], float)
        elements_are_strings = isinstance(sample_preds[0], str)
        return (elements_are_pairs and leaves_are_floats) or elements_are_strings

    def _spacy_preprocess_fn(self, examples: dict) -> dict:
        raise FrameworkCannotHandleTask(
            framework="spaCy", task=self.task_config.pretty_name
        )

    def _extract_spacy_predictions(self, tokens_processed: tuple) -> list:
        raise FrameworkCannotHandleTask(
            framework="spaCy", task=self.task_config.pretty_name
        )


def prepare_test_examples(
    examples: BatchEncoding,
    tokenizer: PreTrainedTokenizerBase,
) -> BatchEncoding:
    """Prepare test examples.

    Args:
        examples (BatchEncoding):
            Dictionary of test examples.
        tokenizer (Hugging Face tokenizer):
            The tokenizer used to preprocess the examples.

    Returns:
        BatchEncoding:
            Dictionary of prepared test examples.
    """
    # Some of the questions have lots of whitespace on the left, which is
    # not useful and will make the truncation of the context fail (the
    # tokenized question will take a lots of space). So we remove that left
    # whitespace
    examples["question"] = [q.lstrip() for q in examples["question"]]

    # Compute the stride, being a quarter of the context length
    stride = tokenizer.model_max_length // 4
    max_length = tokenizer.model_max_length - stride

    # Tokenize our examples with truncation and maybe padding, but keep the
    # overflows using a stride. This results in one example possible giving
    # several features when a context is long, each of those features
    # having a context that overlaps a bit the context of the previous
    # feature.
    tokenized_examples = tokenizer(
        examples["question"],
        examples["context"],
        truncation="only_second",
        max_length=max_length,
        stride=stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding="max_length",
    )

    # Since one example might give us several features if it has a long
    # context, we need a map from a feature to its corresponding example.
    # This key gives us just that.
    sample_mapping = tokenized_examples.pop("overflow_to_sample_mapping")

    # We keep the id that gave us this feature and we will store
    # the offset mappings.
    tokenized_examples["id"] = list()

    for i in range(len(tokenized_examples["input_ids"])):

        # Grab the sequence corresponding to that example (to know what is the
        # context and what is the question).
        sequence_ids = tokenized_examples.sequence_ids(i)
        context_index = 1

        # One example can give several spans, this is the index of the example
        # containing this span of text.
        sample_index = sample_mapping[i]
        tokenized_examples["id"].append(examples["id"][sample_index])

        # Set to (-1, -1) the offset_mapping that are not part of the context so
        # it's easy to determine if a token position is part of the context or not.
        tokenized_examples["offset_mapping"][i] = [
            (o if sequence_ids[k] == context_index else (-1, -1))
            for k, o in enumerate(tokenized_examples["offset_mapping"][i])
        ]

    return tokenized_examples


def postprocess_predictions(
    predictions: Sequence,
    dataset: Dataset,
    prepared_dataset: Dataset,
    cls_token_index: int,
) -> List[dict]:
    """Postprocess the predictions, to allow easier metric computation.

    Args:
        predictions (Sequence):
            The predictions to postprocess.
        dataset (Dataset):
            The dataset containing the examples.
        prepared_dataset (Dataset):
            The dataset containing the prepared examples.
        cls_token_index (int):
            The index of the CLS token.

    Returns:
        list of dicts:
            The postprocessed predictions.
    """
    # Extract the logits from the predictions
    all_start_logits = np.asarray(predictions)[:, :, 0]
    all_end_logits = np.asarray(predictions)[:, :, 1]

    # Build a map from an example to its corresponding features
    id_to_index = {k: i for i, k in enumerate(dataset["id"])}
    features_per_example = defaultdict(list)
    for i, feature in enumerate(prepared_dataset):
        id = feature["id"]
        example_index = id_to_index[id]
        features_per_example[example_index].append(i)

    # Loop over all the examples
    predictions = list()
    for example_index, example in enumerate(dataset):

        # Extract the indices of the features associated with the current example
        feature_indices = features_per_example[example_index]

        # Extract the context
        context = example["context"]

        # Loop through all the features associated to the current example
        min_null_score = 0.0
        valid_answers = list()
        for feature_index in feature_indices:

            # Get the features associated with the current example
            features = prepared_dataset[feature_index]

            # Get the predictions of the model for this feature
            start_logits = all_start_logits[feature_index]
            end_logits = all_end_logits[feature_index]

            # Get the offset mapping, which will allow us to map the positions in
            # our logits to span of texts in the original context
            offset_mapping = features["offset_mapping"]

            # Update minimum null prediction
            cls_index = features["input_ids"].index(cls_token_index)
            feature_null_score = start_logits[cls_index] + end_logits[cls_index]
            if min_null_score < feature_null_score:
                min_null_score = feature_null_score

            # Go through all possibilities for the `n_best_size` greater start and
            # end logits
            n_best_size = 20
            start_indexes = np.argsort(start_logits)[
                -1 : -n_best_size - 1 : -1
            ].tolist()
            end_indexes = np.argsort(end_logits)[-1 : -n_best_size - 1 : -1].tolist()

            for start_index in start_indexes:
                for end_index in end_indexes:

                    # Do not consider out-of-scope answers, either because the
                    # indices are out of bounds or correspond to part of the
                    # input_ids that are not in the context
                    if (
                        start_index >= len(offset_mapping)
                        or end_index >= len(offset_mapping)
                        or offset_mapping[start_index] == -1
                        or offset_mapping[end_index] == -1
                    ):
                        continue

                    # Do not consider answers with a length that is either negative
                    # or greater than the context length
                    max_answer_length = 30
                    max_val = max_answer_length + start_index - 1
                    if end_index < start_index or end_index > max_val:
                        continue

                    start_char = offset_mapping[start_index][0]
                    end_char = offset_mapping[end_index][1]
                    score = start_logits[start_index] + end_logits[end_index]
                    text = context[start_char:end_char]

                    valid_answers.append(dict(score=score, text=text))

        if len(valid_answers) > 0:
            best_answer = sorted(valid_answers, key=lambda x: x["score"], reverse=True)[
                0
            ]

        # In the very rare edge case we have not a single non-null
        # prediction, we create a fake prediction to avoid failure
        else:
            best_answer = {"text": "", "score": 0.0}

        # We pick our final answer as the best one or the null answer
        if best_answer["score"] > min_null_score:
            prediction_text = best_answer["text"]
        else:
            prediction_text = ""

        # Create the final prediction dictionary, to be added to the list of
        # predictions
        prediction = dict(
            id=example["id"],
            prediction_text=prediction_text,
            no_answer_probability=0.0,
        )

        # Add the answer to the list of predictions
        predictions.append(prediction)

    return predictions


def postprocess_labels(dataset: Dataset) -> List[dict]:
    """Postprocess the labels, to allow easier metric computation.

    Args:
        dataset (Dataset):
            The dataset containing the examples.

    Returns:
        list of dicts:
             The postprocessed labels.
    """
    labels = list()
    for example in dataset:

        # Create the associated reference dictionary, to be added to the list of
        # references
        label = dict(
            id=example["id"],
            answers=dict(
                text=example["answers"]["text"],
                answer_start=example["answers"]["answer_start"],
            ),
        )

        # Add the answer and label to the list of predictions and labels, respectively
        labels.append(label)

    return labels
