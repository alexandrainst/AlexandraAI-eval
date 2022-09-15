"""Utility functions related to loading local models."""

import inspect
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints

import torch
import torch.nn as nn
from transformers.models.auto.tokenization_auto import AutoTokenizer
from transformers.tokenization_utils_base import PreTrainedTokenizerBase

from .config import ModelConfig, TaskConfig
from .enums import Framework
from .model_adjustment import adjust_model_to_task


def load_local_pytorch_model(
    model_config: ModelConfig,
    device: str,
    task_config: TaskConfig,
    architecture_fname: Optional[Union[str, Path]] = None,
    weight_fname: Optional[Union[str, Path]] = None,
) -> Dict[str, Union[nn.Module, PreTrainedTokenizerBase]]:
    """Load a local PyTorch model from a path.

    Args:
        model_config (ModelConfig):
            The configuration of the model.
        device (str):
            Device to load the model onto.
        task_config (TaskConfig):
            The task configuration.
        architecture_fname (str or Path or None, optional):
            Name of the file containing the model architecture, which is located inside
            the model folder. If None then the first Python script found in the model
            folder will be used. Defaults to None.
        weight_fname (str or Path or None, optional):
            Name of the file containing the model weights, which is located inside
            the model folder. If None then the first file found in the model folder
            ending with ".bin" will be used. Defaults to None.
        config_fname (str or Path or None, optional):
            Name of the file containing the model configuration, which is located
            inside the model folder. If None then the first file found in the model
            folder ending with ".json" will be used. If no file is found then the the
            configuration will be taken from the task configuration. In other words,
            assume that the model is configured in the same way as the dataset.
            Defaults to None.

    Returns:
        dict:
            A dictionary containing the model and tokenizer.
    """
    # Ensure that the model_folder is a Path object
    model_folder = Path(model_config.model_id)

    # Add the model folder to PATH
    sys.path.insert(0, str(model_folder))

    # If no architecture_fname is provided, then use the first Python script found
    if architecture_fname is None:
        architecture_path = next(model_folder.glob("*.py"))
    else:
        architecture_path = model_folder / architecture_fname

    # If no weight_fname is provided, then use the first file found ending with ".bin"
    if weight_fname is None:
        weight_path = next(model_folder.glob("*.bin"))
    else:
        weight_path = model_folder / weight_fname

    # Import the module containing the model architecture
    module_name = architecture_path.stem
    module = import_module(module_name)

    # Get the candidates for the model architecture class, being all classes in the
    # loaded module that are subclasses of `torch.nn.Module`, and which come from the
    # desired module (as opposed to being imported from elsewhere)
    model_candidates = [
        obj
        for _, obj in module.__dict__.items()
        if isinstance(obj, type)
        and issubclass(obj, nn.Module)
        and obj.__module__ == module_name
    ]

    # If there are no candidates, raise an error
    if not model_candidates:
        raise ValueError(f"No model architecture found in {architecture_path}")

    # Pick the first candidate
    model_cls = model_candidates[0]

    # Get the arguments for the class initializer
    model_args = list(inspect.signature(model_cls).parameters)

    # Remove the arguments that have default values
    defaults_tuple = model_cls.__init__.__defaults__  # type: ignore[misc]
    model_args = model_args[: -len(defaults_tuple)]

    # Get the type hints for the class initializer
    type_hints = get_type_hints(model_cls.__init__)  # type: ignore[misc]

    # If any of the arguments are not in the type hints, raise an error
    for arg in model_args:
        if arg not in type_hints:
            raise ValueError(
                f"A type hint or default value for the {arg!r} argument of the "
                f"{model_cls.__name__!r} class is missing. Please specify either "
                f"in the {architecture_path.name!r} file."
            )

    # Fetch the model keyword arguments from the local configuration
    model_kwargs = {
        arg: get_from_config(
            key=arg,
            expected_type=type_hints[arg],
            model_folder=model_folder,
        )
        for arg in model_args
    }

    # Initialize the model with the (potentiall empty) set of keyword arguments
    model = model_cls(**model_kwargs)

    # Load the model weights
    state_dict = torch.load(weight_path, map_location=torch.device("cpu"))
    model.load_state_dict(state_dict)

    # Set the model to evaluation mode, making its predictions deterministic
    model.eval()

    # Move the model to the specified device
    model.to(device)

    # Adjust the model to the task
    adjust_model_to_task(
        model=model,
        model_config=model_config,
        task_config=task_config,
    )

    # Load the tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_config.tokenizer_id)

    # Return the model with the loaded weights
    return dict(model=model, tokenizer=tokenizer)


def model_exists_locally(
    model_id: Union[str, Path],
    architecture_fname: Optional[Union[str, Path]] = None,
    weight_fname: Optional[Union[str, Path]] = None,
) -> bool:
    """Check if a model exists locally.

    Args:
        model_id (str or Path):
            Path to the model folder.
        architecture_fname (str or Path or None, optional):
            Name of the file containing the model architecture, which is located inside
            the model folder. If None then the first Python script found in the model
            folder will be used. Defaults to None.
        weight_fname (str or Path or None, optional):
            Name of the file containing the model weights, which is located inside
            the model folder. If None then the first file found in the model folder
            ending with ".bin" will be used. Defaults to None.

    Returns:
        bool:
            Whether the model exists locally.
    """
    # Ensure that the model_folder is a Path object
    model_folder = Path(model_id)

    # If no architecture_fname is provided, then use the first Python script found
    if architecture_fname is None:
        try:
            architecture_path = next(model_folder.glob("*.py"))
        except StopIteration:
            return False
    else:
        architecture_path = model_folder / architecture_fname

    # If no weight_fname is provided, then use the first file found ending with ".bin"
    if weight_fname is None:
        try:
            weight_path = next(model_folder.glob("*.bin"))
        except StopIteration:
            return False
    else:
        weight_path = model_folder / weight_fname

    # Check if the model architecture and weights exist
    return architecture_path.exists() and weight_path.exists()


def get_model_config_locally(
    model_folder: Union[str, Path],
    dataset_id2label: List[str],
) -> ModelConfig:
    """Get the model configuration from a local model.

    Args:
        model_folder (str or Path):
            Path to the model folder.
        dataset_id2label (list of str):
            List of labels in the dataset.

    Returns:
        ModelConfig:
            The model configuration.
    """
    return ModelConfig(
        model_id=Path(model_folder).name,
        tokenizer_id=get_from_config(
            key="tokenizer_id",
            expected_type=str,
            model_folder=model_folder,
            user_prompt="Please specify the Hugging Face ID of the tokenizer to use: ",
        ),
        revision="",
        framework=Framework.PYTORCH,
        id2label=get_from_config(
            key="id2label",
            expected_type=list,
            model_folder=model_folder,
            user_prompt="Please specify the labels in the order the model was trained "
            "(comma-separated), or press enter to use the default values "
            f"[{', '.join(dataset_id2label)}]: ",
            user_prompt_default_value=dataset_id2label,
        ),
    )


def get_from_config(
    key: str,
    expected_type: Type,
    model_folder: Union[str, Path],
    default_value: Optional[Any] = None,
    user_prompt: Optional[str] = None,
    user_prompt_default_value: Optional[Any] = None,
) -> Any:
    """Get an attribute from the local model configuration.

    If the attribute is not found in the local model configuration, then the user
    will be prompted to enter it, after which it will be saved to the local model
    configuration. If the configuration file does not exist, then a new one will be
    created named `config.json`.

    Args:
        key (str):
            The key to get from the configuration.
        expected_type (Type):
            The expected type of the value.
        model_folder (str or Path):
            Path to the model folder.
        default_value (Any or None, optional):
            The default value to use if the attribute is not found in the local model
            configuration. If None then the user will be prompted to enter the value.
            Defaults to None.
        user_prompt (str or None, optional):
            The prompt to show the user when asking for the value. If None then the
            prompt will be automatically generated. Defaults to None.
        user_prompt_default_value (Any or None, optional):
            The default value that a user can press Enter to use, when prompted. If
            None then the user cannot choose a default value. Defaults to None.

    Returns:
        Any:
            The value of the key, of data type `expected_type`.
    """
    # Ensure that the model_folder is a Path object
    model_folder = Path(model_folder)

    # Get the candidate configuration files
    config_paths = list(model_folder.glob("*.json"))

    # If there isn't a config then we set it to a blank dictionary. Otherwise, we load
    # the config file
    if not config_paths:
        config_path = model_folder / "config.json"
        config = dict()
    else:
        config_path = config_paths[0]
        config = json.loads(config_path.read_text())

    # If the key is not in the config then we either use the default value or prompt
    # the user to enter it
    if key not in config:

        # If the default value is set and is of the correct type, then we use it
        if default_value is not None and isinstance(default_value, expected_type):
            config[key] = default_value

        # Otherwise, we prompt the user to enter the value
        else:
            if user_prompt is None:

                # Define the base user prompt
                base_prompt = (
                    "The configuration did not contain the {key!r} entry. Please "
                    "specify its value"
                )
                if user_prompt_default_value is not None:
                    user_prompt = (
                        "The configuration did not contain the {key!r} entry. Press "
                        "Enter to use the default value {user_prompt_default_value!r} "
                        "or specify a new value"
                    )

                if expected_type is bool:
                    user_prompt = f"{base_prompt} (true/false): "
                elif expected_type is list:
                    user_prompt = f"{base_prompt} (comma-separated): "
                elif expected_type is dict:
                    user_prompt = f"{base_prompt} (key=value, comma-separated): "
                else:
                    user_prompt = f"{base_prompt}: "

            # Prompt the user to enter the value
            user_input = input(user_prompt)

            # If the user input is blank (i.e. they pressed Enter) and there is a
            # default value, then we use the default value
            if not user_input and user_prompt_default_value is not None:
                config[key] = user_prompt_default_value

            # Otherwise, we parse the user input, depending on the expected type
            else:
                if expected_type is str:
                    config[key] = user_input
                elif expected_type is int:
                    config[key] = int(user_input)
                elif expected_type is float:
                    config[key] = float(user_input)
                elif expected_type is bool:
                    config[key] = user_input.lower() == "true"
                elif expected_type is list:
                    config[key] = user_input.split()
                elif expected_type is dict:
                    config[key] = dict(
                        item.split("=") for item in user_input.split(",")
                    )

        # Save the new modified config
        if not config_path.exists():
            config_path.touch()
        config_path.write_text(json.dumps(config, indent=4))

    # Return the value of the key
    return config[key]