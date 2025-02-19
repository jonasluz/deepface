import os
from typing import Union, Tuple, List
import base64
from pathlib import Path

# 3rd party dependencies
from PIL import Image
import requests
import numpy as np
import cv2
import tensorflow as tf

# package dependencies
from deepface.detectors import DetectorWrapper
from deepface.models.Detector import DetectedFace, FacialAreaRegion
from deepface.commons.logger import Logger

logger = Logger(module="commons.functions")

# pylint: disable=no-else-raise

# --------------------------------------------------
# configurations of dependencies


def get_tf_major_version() -> int:
    return int(tf.__version__.split(".", maxsplit=1)[0])


tf_major_version = get_tf_major_version()

if tf_major_version == 1:
    from keras.preprocessing import image
elif tf_major_version == 2:
    from tensorflow.keras.preprocessing import image

# --------------------------------------------------


def initialize_folder() -> None:
    """Initialize the folder for storing weights and models.

    Raises:
        OSError: if the folder cannot be created.
    """
    home = get_deepface_home()
    deepFaceHomePath = home + "/.deepface"
    weightsPath = deepFaceHomePath + "/weights"

    if not os.path.exists(deepFaceHomePath):
        os.makedirs(deepFaceHomePath, exist_ok=True)
        logger.info(f"Directory {home}/.deepface created")

    if not os.path.exists(weightsPath):
        os.makedirs(weightsPath, exist_ok=True)
        logger.info(f"Directory {home}/.deepface/weights created")


def get_deepface_home() -> str:
    """Get the home directory for storing weights and models.

    Returns:
        str: the home directory.
    """
    return str(os.getenv("DEEPFACE_HOME", default=str(Path.home())))


# --------------------------------------------------


def loadBase64Img(uri: str) -> np.ndarray:
    """Load image from base64 string.

    Args:
        uri: a base64 string.

    Returns:
        numpy array: the loaded image.
    """
    encoded_data = uri.split(",")[1]
    nparr = np.fromstring(base64.b64decode(encoded_data), np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    # img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return img_bgr


def load_image(img: Union[str, np.ndarray]) -> Tuple[np.ndarray, str]:
    """
    Load image from path, url, base64 or numpy array.
    Args:
        img: a path, url, base64 or numpy array.
    Returns:
        image (numpy array): the loaded image in BGR format
        image name (str): image name itself
    """

    # The image is already a numpy array
    if isinstance(img, np.ndarray):
        return img, "numpy array"

    if isinstance(img, Path):
        img = str(img)

    if not isinstance(img, str):
        raise ValueError(f"img must be numpy array or str but it is {type(img)}")

    # The image is a base64 string
    if img.startswith("data:image/"):
        return loadBase64Img(img), "base64 encoded string"

    # The image is a url
    if img.startswith("http"):
        return (
            np.array(Image.open(requests.get(img, stream=True, timeout=60).raw).convert("BGR")),
            # return url as image name
            img,
        )

    # The image is a path
    if os.path.isfile(img) is not True:
        raise ValueError(f"Confirm that {img} exists")

    # image must be a file on the system then

    # image name must have english characters
    if img.isascii() is False:
        raise ValueError(f"Input image must not have non-english characters - {img}")

    img_obj_bgr = cv2.imread(img)
    # img_obj_rgb = cv2.cvtColor(img_obj_bgr, cv2.COLOR_BGR2RGB)
    return img_obj_bgr, img


# --------------------------------------------------


def extract_faces(
    img: Union[str, np.ndarray],
    target_size: tuple = (224, 224),
    detector_backend: str = "opencv",
    grayscale: bool = False,
    enforce_detection: bool = True,
    align: bool = True,
) -> List[Tuple[np.ndarray, dict, float]]:
    """
    Extract faces from an image.
    Args:
        img: a path, url, base64 or numpy array.
        target_size (tuple, optional): the target size of the extracted faces.
        Defaults to (224, 224).
        detector_backend (str, optional): the face detector backend. Defaults to "opencv".
        grayscale (bool, optional): whether to convert the extracted faces to grayscale.
        Defaults to False.
        enforce_detection (bool, optional): whether to enforce face detection. Defaults to True.
        align (bool, optional): whether to align the extracted faces. Defaults to True.

    Raises:
        ValueError: if face could not be detected and enforce_detection is True.

    Returns:
        results (List[Tuple[np.ndarray, dict, float]]): A list of tuples
            where each tuple contains:
            - detected_face (np.ndarray): The detected face as a NumPy array.
            - face_region (dict): The image region represented as
                {"x": x, "y": y, "w": w, "h": h}
            - confidence (float): The confidence score associated with the detected face.
    """

    # this is going to store a list of img itself (numpy), it region and confidence
    extracted_faces = []

    # img might be path, base64 or numpy array. Convert it to numpy whatever it is.
    img, img_name = load_image(img)

    base_region = FacialAreaRegion(x=0, y=0, w=img.shape[1], h=img.shape[0])

    if detector_backend == "skip":
        face_objs = [DetectedFace(img=img, facial_area=base_region, confidence=0)]
    else:
        face_objs = DetectorWrapper.detect_faces(detector_backend, img, align)

    # in case of no face found
    if len(face_objs) == 0 and enforce_detection is True:
        if img_name is not None:
            raise ValueError(
                f"Face could not be detected in {img_name}."
                "Please confirm that the picture is a face photo "
                "or consider to set enforce_detection param to False."
            )
        else:
            raise ValueError(
                "Face could not be detected. Please confirm that the picture is a face photo "
                "or consider to set enforce_detection param to False."
            )

    if len(face_objs) == 0 and enforce_detection is False:
        face_objs = [DetectedFace(img=img, facial_area=base_region, confidence=0)]

    for face_obj in face_objs:
        current_img = face_obj.img
        current_region = face_obj.facial_area
        confidence = face_obj.confidence
        if current_img.shape[0] > 0 and current_img.shape[1] > 0:
            if grayscale is True:
                current_img = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)

            # resize and padding
            factor_0 = target_size[0] / current_img.shape[0]
            factor_1 = target_size[1] / current_img.shape[1]
            factor = min(factor_0, factor_1)

            dsize = (
                int(current_img.shape[1] * factor),
                int(current_img.shape[0] * factor),
            )
            current_img = cv2.resize(current_img, dsize)

            diff_0 = target_size[0] - current_img.shape[0]
            diff_1 = target_size[1] - current_img.shape[1]
            if grayscale is False:
                # Put the base image in the middle of the padded image
                current_img = np.pad(
                    current_img,
                    (
                        (diff_0 // 2, diff_0 - diff_0 // 2),
                        (diff_1 // 2, diff_1 - diff_1 // 2),
                        (0, 0),
                    ),
                    "constant",
                )
            else:
                current_img = np.pad(
                    current_img,
                    (
                        (diff_0 // 2, diff_0 - diff_0 // 2),
                        (diff_1 // 2, diff_1 - diff_1 // 2),
                    ),
                    "constant",
                )

            # double check: if target image is not still the same size with target.
            if current_img.shape[0:2] != target_size:
                current_img = cv2.resize(current_img, target_size)

            # normalizing the image pixels
            # what this line doing? must?
            img_pixels = image.img_to_array(current_img)
            img_pixels = np.expand_dims(img_pixels, axis=0)
            img_pixels /= 255  # normalize input in [0, 1]

            # int cast is for the exception - object of type 'float32' is not JSON serializable
            region_obj = {
                "x": current_region.x,
                "y": current_region.y,
                "w": current_region.w,
                "h": current_region.h,
            }

            extracted_face = (img_pixels, region_obj, confidence)
            extracted_faces.append(extracted_face)

    if len(extracted_faces) == 0 and enforce_detection == True:
        raise ValueError(
            f"Detected face shape is {img.shape}. Consider to set enforce_detection arg to False."
        )

    return extracted_faces


def normalize_input(img: np.ndarray, normalization: str = "base") -> np.ndarray:
    """Normalize input image.

    Args:
        img (numpy array): the input image.
        normalization (str, optional): the normalization technique. Defaults to "base",
        for no normalization.

    Returns:
        numpy array: the normalized image.
    """

    # issue 131 declares that some normalization techniques improves the accuracy

    if normalization == "base":
        return img

    # @trevorgribble and @davedgd contributed this feature
    # restore input in scale of [0, 255] because it was normalized in scale of
    # [0, 1] in preprocess_face
    img *= 255

    if normalization == "raw":
        pass  # return just restored pixels

    elif normalization == "Facenet":
        mean, std = img.mean(), img.std()
        img = (img - mean) / std

    elif normalization == "Facenet2018":
        # simply / 127.5 - 1 (similar to facenet 2018 model preprocessing step as @iamrishab posted)
        img /= 127.5
        img -= 1

    elif normalization == "VGGFace":
        # mean subtraction based on VGGFace1 training data
        img[..., 0] -= 93.5940
        img[..., 1] -= 104.7624
        img[..., 2] -= 129.1863

    elif normalization == "VGGFace2":
        # mean subtraction based on VGGFace2 training data
        img[..., 0] -= 91.4953
        img[..., 1] -= 103.8827
        img[..., 2] -= 131.0912

    elif normalization == "ArcFace":
        # Reference study: The faces are cropped and resized to 112×112,
        # and each pixel (ranged between [0, 255]) in RGB images is normalised
        # by subtracting 127.5 then divided by 128.
        img -= 127.5
        img /= 128
    else:
        raise ValueError(f"unimplemented normalization type - {normalization}")

    return img


def find_target_size(model_name: str) -> tuple:
    """Find the target size of the model.

    Args:
        model_name (str): the model name.

    Returns:
        tuple: the target size.
    """

    target_sizes = {
        "VGG-Face": (224, 224),
        "Facenet": (160, 160),
        "Facenet512": (160, 160),
        "OpenFace": (96, 96),
        "DeepFace": (152, 152),
        "DeepID": (47, 55),
        "Dlib": (150, 150),
        "ArcFace": (112, 112),
        "SFace": (112, 112),
    }

    target_size = target_sizes.get(model_name)

    if target_size == None:
        raise ValueError(f"unimplemented model name - {model_name}")

    return target_size
