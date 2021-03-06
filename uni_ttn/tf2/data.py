import pickle as pk
import numpy as np
import tensorflow as tf
import math, scipy
import tensorflow_datasets as tfds

try:
    import skimage.transform
    from skimage.util import img_as_float
except ImportError:
    pass

try: import torch
except ImportError: pass


class DataGenerator:
    def __init__(self, dataset='MNIST'):
        print(f'Loading {dataset}...')
        if dataset == 'MNIST':
            mnist_data = tf.keras.datasets.mnist.load_data()
            self.train_images = mnist_data[0][0]
            self.train_labels = mnist_data[0][1]
            self.test_images = mnist_data[1][0]
            self.test_labels = mnist_data[1][1]
        elif dataset == 'Fashion_MNIST':
            fashion_data = tf.keras.datasets.fashion_mnist.load_data()
            self.train_images = fashion_data[0][0]
            self.train_labels = fashion_data[0][1]
            self.test_images = fashion_data[1][0]
            self.test_labels = fashion_data[1][1]
        elif dataset == 'CIFAR':
            cifar_data = tf.keras.datasets.cifar10.load_data()
            self.train_images = cifar_data[0][0]
            self.train_labels = cifar_data[0][1].squeeze()
            self.test_images = cifar_data[1][0]
            self.test_labels = cifar_data[1][1].squeeze()
            self.convert_to_grayscale()
        elif dataset == 'KMNIST':
            dataset = tfds.load('kmnist', shuffle_files=False, try_gcs=False)
            train, test = dataset['train'], dataset['test']
            train_numpy = np.vstack(tfds.as_numpy(train))
            test_numpy = np.vstack(tfds.as_numpy(test))
            train_images = np.array(list(map(lambda x: x[0]['image'], train_numpy))).squeeze()
            train_labels = np.array(list(map(lambda x: x[0]['label'], train_numpy)))
            test_images = np.array(list(map(lambda x: x[0]['image'], test_numpy))).squeeze()
            test_labels = np.array(list(map(lambda x: x[0]['label'], test_numpy)))
            # There appears to be a distribution shift in the test set; shuffle and regroup training and testing sets
            images = np.concatenate([train_images, test_images], axis=0)
            labels = np.concatenate([train_labels, test_labels], axis=0)
            images, labels = shuffle(images, labels)
            self.train_images, self.test_images = images[:60000], images[60000:]
            self.train_labels, self.test_labels = labels[:60000], labels[60000:]
        else:
            raise NotImplementedError

    def convert_to_grayscale(self):
        self.train_images = convert_to_grayscale(self.train_images)
        self.test_images = convert_to_grayscale(self.test_images)

    def shrink_images(self, new_shape):
        self.train_images = resize_images(self.train_images, new_shape)
        self.test_images = resize_images(self.test_images, new_shape)

    def featurize(self, dim):
        self.train_images = trig_featurize(self.train_images, dim)
        self.test_images = trig_featurize(self.test_images, dim)

    def featurize_qubit(self):
        self.train_images = trig_featurize_qubit(self.train_images)
        self.test_images = trig_featurize_qubit(self.test_images)

    def featurize_exp(self):
        self.train_images = exp_featurize(self.train_images)
        self.test_images = exp_featurize(self.test_images)

    def get_principle_components(self, k=8, digits=(3,5)):
        if digits:
            self.train_images, self.train_labels = select_digits(self.train_images, self.train_labels, digits)
            self.test_images, self.test_labels = select_digits(self.test_images, self.test_labels, digits)
        self.train_images, self.test_images = pca(self.train_images, self.test_images, k=k)

    def export(self, path):
        train_dest = path + '_train'
        test_dest = path + '_test'
        save_data(self.train_images, self.train_labels, train_dest)
        save_data(self.test_images, self.test_labels, test_dest)

def convert_to_grayscale(images):
    '''Red * 0.3 + Green * 0.59 + Blue * 0.11'''
    return images[:, :, :, 0]*0.3 + images[:, :, :, 0]*0.59 + images[:, :, :, 0]*0.11

def pca(train_images, test_images, k=8):
    images = np.concatenate([train_images, test_images], axis=0)
    images = flatten_images(img_as_float(images))
    images = images - np.mean(images, axis=0, keepdims=True)

    image_size = images.shape[1]
    cov_mat = np.matmul(images.T, images)
    eigenvectors = scipy.linalg.eigh(cov_mat, eigvals=(image_size-k, image_size-1))[1]

    projected = np.matmul(images, eigenvectors)
    normal_projected = normalize(projected)
    return normal_projected[:len(train_images)], normal_projected[len(train_images):]


def select_digits(images, labels, digits):
    assert len(digits) == 2
    if isinstance(digits[0], int):
        cumulative_test = (labels == digits[0])
        for digit in digits[1:]:
            digit_test = (labels == digit)
            cumulative_test = np.logical_or(digit_test, cumulative_test)
        valid_images = images[cumulative_test]
        valid_labels = labels[cumulative_test]
        return valid_images, valid_labels
    elif digits[0] == ('even' or 'odd'):
        binary_labels = labels % 2
        return images, binary_labels
    elif isinstance(digits[0], list):
        assert not any(np.isin(digits[0], digits[1]))
        cumulative_test = (labels == digits[0][0])
        for digit in digits[0][1:]:
            digit_test = (labels == digit)
            cumulative_test = np.logical_or(digit_test, cumulative_test)
        class_0_images = images[cumulative_test]
        class_0_labels = np.zeros(len(class_0_images), dtype=np.int32)

        cumulative_test = (labels == digits[1][0])
        for digit in digits[1][1:]:
            digit_test = (labels == digit)
            cumulative_test = np.logical_or(digit_test, cumulative_test)
        class_1_images = images[cumulative_test]
        class_1_labels = np.ones(len(class_1_images), dtype=np.int32)

        images = np.concatenate([class_0_images, class_1_images], axis=0)
        labels = np.concatenate([class_0_labels, class_1_labels], axis=0)
        return shuffle(images, labels)


def shuffle(images, labels):
    num_images = len(images)
    random_perm = np.random.permutation(num_images)
    randomized_images = images[random_perm]
    randomized_labels = labels[random_perm]
    return randomized_images, randomized_labels


def resize_images(images, shape):
    num_images = images.shape[0]
    new_images_shape = (num_images, shape[0], shape[1])
    new_images = skimage.transform.resize(
        images,
        new_images_shape,
        anti_aliasing=True,
        mode='constant')
    return new_images


def batch_generator_tf(images: tf.constant, labels: tf.constant, batch_size):
    num_images = images.shape[0]
    indices = tf.range(0, num_images, dtype=tf.int32)
    shuffled_indices = tf.random.shuffle(indices)
    randomized_images = tf.gather(images, shuffled_indices)
    randomized_labels = tf.gather(labels, shuffled_indices)

    for i in range(0, num_images, batch_size):
        batch_images = randomized_images[i:i + batch_size]
        batch_labels = randomized_labels[i:i + batch_size]
        yield batch_images, batch_labels


def batch_generator_np(images: np.ndarray or torch.tensor, labels: np.ndarray or torch.tensor, batch_size):
    num_images = len(images)
    if isinstance(images, np.ndarray): random_perm = np.random.permutation(num_images)
    elif isinstance(images, torch.Tensor): random_perm = torch.randperm(num_images)
    else: raise NotImplementedError
    randomized_images = images[random_perm]
    randomized_labels = labels[random_perm]

    for i in range(0, num_images, batch_size):
        batch_images = randomized_images[i: i + batch_size]
        batch_labels = randomized_labels[i: i + batch_size]
        yield batch_images, batch_labels


def flatten_images(images):
    num_images = len(images)
    flattened_image = np.reshape(images, [num_images, -1])
    return flattened_image


def exp_featurize(images):
    flat_images = flatten_images(images)
    (num_images, num_pixels) = flat_images.shape
    prep_axes = np.reshape(flat_images, (num_images, num_pixels, 1))
    pix_copy = np.tile(prep_axes, [1, 1, 2])
    pix_copy[:, :, 0] = 1 / np.sqrt(pix_copy[:, :, 0] ** 2 + 1)
    pix_copy[:, :, 1] = pix_copy[:, :, 1] / np.sqrt(pix_copy[:, :, 1] ** 2 + 1)
    return pix_copy


def trig_featurize_qubit(images):
    flat_images = flatten_images(images)
    (num_images, num_pixels) = flat_images.shape
    prep_axes = np.reshape(flat_images, (num_images, num_pixels, 1))
    pix_copy = np.tile(prep_axes, [1, 1, 2])
    pix_copy[:, :, 0] = np.cos(pix_copy[:, :, 0] * np.pi / 2)
    pix_copy[:, :, 1] = np.sin(pix_copy[:, :, 1] * np.pi / 2)
    return pix_copy


def reverse_trig_featurize_qubit(featurized_images):
    raw_pixels = np.reshape(np.arccos(featurized_images[:, :, 0]), [-1, 8, 8])
    return raw_pixels


def trig_featurize(images, dim):
    flat_images = flatten_images(images)
    (num_images, num_pixels) = flat_images.shape
    prep_axes = np.reshape(flat_images, (num_images, num_pixels, 1))
    pix_copy = np.tile(prep_axes, [1, 1, dim])

    d = dim
    for s in range(1, dim + 1):
        pix_copy[:, :, s - 1] = np.sqrt(
            float(math.factorial(d - 1)) / \
            float(math.factorial(s - 1) * math.factorial(d - s))
        ) \
        * np.cos(pix_copy[:, :, s - 1] * np.pi / 2) ** (d - s) \
        * np.sin(pix_copy[:, :, s - 1] * np.pi / 2) ** (s - 1)

    return pix_copy


def split_data(images, labels, split):
    num_images = len(images)
    split_point = int((1 - split) * num_images)
    true_train_data = (images[:split_point], labels[:split_point])
    val_data = (images[split_point:], labels[split_point:])
    return true_train_data, val_data


def binary_labels(labels):
    max_digit = np.amax(labels)
    binary_values = np.floor_divide(labels, max_digit)
    binary_labels = one_hot(binary_values)
    return binary_labels


def one_hot(bin_labels):
    length = np.amax(bin_labels) + 1
    blank = np.zeros(bin_labels.size * length)
    multiples = np.arange(bin_labels.size)
    index_shift = length * multiples
    new_indices = bin_labels + index_shift
    blank[new_indices] = 1
    matrix_blank = np.reshape(blank, [bin_labels.size, length])
    return matrix_blank


def get_data_file(data_path, digits, val_split, sample_size=None):
    print(f'Load Data From File: {data_path}')
    (train_raw_im, train_raw_lab) = load_data(data_path + '_train')
    (test_raw_im, test_raw_lab) = load_data(data_path + '_test')
    return process(train_raw_im, train_raw_lab, test_raw_im, test_raw_lab,
                   digits, val_split, sample_size=sample_size)


def get_data_web(digits, val_split, size, dim, sample_size=None, dataset='Fashion_MNIST'):
    print(f'Fetch Data From Web - {dataset}')
    data = DataGenerator(dataset=dataset)
    data.shrink_images(size)
    # data.featurize(dim)
    data.featurize_qubit()
    train_raw_im, train_raw_lab = data.train_images, data.train_labels
    test_raw_im, test_raw_lab = data.test_images, data.test_labels
    return process(train_raw_im, train_raw_lab, test_raw_im, test_raw_lab,
                   digits, val_split, sample_size=sample_size)


def process(train_raw_im, train_raw_lab, test_raw_im, test_raw_lab,
            digits, val_split, sample_size=None):
    (train_images, train_labels_int) = select_digits(train_raw_im, train_raw_lab, digits)
    (test_images, test_labels_int) = select_digits(test_raw_im, test_raw_lab, digits)
    if sample_size:
        assert sample_size > 0
        train_images, train_labels_int = train_images[0:sample_size], train_labels_int[0:sample_size]
        test_images, test_labels_int = test_images[0:sample_size], test_labels_int[0:sample_size]

    train_labels = binary_labels(train_labels_int)
    test_labels = binary_labels(test_labels_int)

    if val_split:
        assert val_split > 0
        (true_train_data, val_data) = split_data(train_images, train_labels, val_split)
        return true_train_data, val_data, (test_images, test_labels)
    else:
        return (train_images, train_labels), None, (test_images, test_labels)


def normalize(images):
    images -= np.min(images)
    images /= np.max(images)
    return images


def save_data(images, labels, path):
    dest = open(path, 'wb')
    data = (images, labels)
    pk.dump(data, dest, protocol=2)


def load_data(path):
    dest = open(path, 'rb')
    data = pk.load(dest)
    return data


if __name__ == '__main__':
    from matplotlib import pyplot as plt

    # data1 = DataGenerator()
    # data1.shrink_images([8, 8])
    # dim = 2
    # data1.featurize(dim)

    data2 = DataGenerator(dataset='KMNIST')
    data2.shrink_images([8, 8])
    data2.featurize_qubit()
    data2.export('/home/haoranliao/dephased_ttn_project/datasets/kmnist8x8/kmnist8x8')

    # data4 = DataGenerator()
    # data4.get_principle_components(digits=(2,7))
    # data4.featurize_qubit()
    # data4.export('/home/haoranliao/dephased_ttn_project/datasets/mnist8pca_dig27/mnist8pca_dig27')
