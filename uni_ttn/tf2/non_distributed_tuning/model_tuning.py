'''
https://github.com/ray-project/ray/blob/master/python/ray/tune/examples/tf_mnist_example.py
'''

import tensorflow as tf
import numpy as np
import os, yaml, json
from tqdm import tqdm
from uni_ttn.tf2 import data, model, spsa
from uni_ttn.tf2.model import var_or_const
from ray import tune
try: from ray.tune.suggest.ax import AxSearch
except ImportError: pass

TQDM_DISABLED = True
TQDM_DICT = {'leave': False, 'disable': TQDM_DISABLED, 'position': 0}


class Tuning_Model(model.Model):
    def __init__(self, data_path, digits, val_split, deph_p, num_anc, config, tune_config):
        super().__init__(data_path, digits, val_split, deph_p, num_anc, tune_config['tune_init_std'], tune_config['tune_lr'], config)

        assert self.network.init_std == tune_config['tune_init_std']

        if config['tree']['opt']['opt'] == 'adam':
            if not tune_config.get('tune_lr', False): self.network.opt = tf.keras.optimizers.Adam()
            else: self.network.opt = tf.keras.optimizers.Adam(tune_config['tune_lr'])
        elif config['tree']['opt']['opt'] == 'spsa':
            self.network.opt = spsa.Spsa(self.network, tune_config)
        else:
            raise NotImplementedError

    def run_epoch(self, batch_size, epoch, grad_accumulation=True):
        if not grad_accumulation:
            batch_iter = data.batch_generator_np(self.train_images, self.train_labels, batch_size)
            for (train_image_batch, train_label_batch) in tqdm(batch_iter, total=len(self.train_images)//batch_size, **TQDM_DICT):
                self.network.update_no_processing(train_image_batch, train_label_batch)
        else:
            exec_batch_size = self.config['data']['execute_batch_size']
            counter = batch_size // exec_batch_size
            assert not batch_size % exec_batch_size, 'batch_size not divisible by exec_batch_size'
            batch_iter = data.batch_generator_np(self.train_images, self.train_labels, exec_batch_size)
            for (train_image_batch, train_label_batch) in tqdm(batch_iter, total=len(self.train_images)//exec_batch_size, **TQDM_DICT):
                if counter > 1:
                    counter -= 1
                    self.network.update(train_image_batch, train_label_batch, epoch, apply_grads=False)
                else:
                    counter = batch_size // exec_batch_size
                    self.network.update(train_image_batch, train_label_batch, epoch, apply_grads=True, counter=counter)


class UniTTN(tune.Trainable):
    def setup(self, tune_config):
        import tensorflow as tf     # required by ray tune
        print(os.getcwd())  # the cwd may not be the current file path

        self.tune_config = tune_config
        digits = var_or_const(list_digits, 0)
        deph_p = var_or_const(list_deph_p, 0)
        num_anc = var_or_const(list_num_anc, 0)
        self.model = Tuning_Model(data_path, digits, val_split, deph_p, num_anc, config, tune_config)

    def step(self):
        self.model.run_epoch(batch_size, self.iteration, grad_accumulation=config['data']['grad_accumulation'])
        test_accuracy = self.model.run_network(self.model.test_images, self.model.test_labels, batch_size*self.model.b_factor)
        return {"test_accuracy": test_accuracy * 100}


if __name__ == "__main__":
    with open('./config_example.yaml', 'r') as f:
        config = yaml.load(f, yaml.FullLoader)
        print(json.dumps(config, indent=1), flush=True)

    if config['meta']['set_visible_gpus']:
        os.environ["CUDA_VISIBLE_DEVICES"] = config['meta']['visible_gpus']

    np.random.seed(config['meta']['random_seed'])
    tf.random.set_seed(config['meta']['random_seed'])

    data_path = config['data']['path']
    val_split = config['data']['val_split']
    list_batch_sizes = config['data']['list_batch_sizes']
    list_digits = config['data']['list_digits']
    num_repeat = config['meta']['num_repeat']
    list_epochs = config['meta']['list_epochs']
    list_deph_p = config['meta']['deph']['p']
    list_num_anc = config['meta']['list_num_anc']

    deph_p = var_or_const(list_deph_p, 0)
    num_anc = var_or_const(list_num_anc, 0)
    batch_size = var_or_const(list_batch_sizes, 0)

    asha_scheduler = tune.schedulers.ASHAScheduler(
        time_attr='training_iteration',
        max_t=80,
        grace_period=80
    )

    # ax_search = AxSearch(metric="score")
                         #points_to_evaluate=[
                             #{'num_anc': 0, 'deph_p': 0, 'tune_lr': 0, 'tune_init_std': 1, 'a': 14.206306419883958, 'b': 26.33438842614464, 'A': 1.0, 's': 3.1529545707111484, 't': 1.606894338729561, 'gamma': 0.3942720565688982},
                             #{'num_anc': 0, 'deph_p': 0, 'tune_lr': 0, 'tune_init_std': 1, 'a': 14.618012336082757, 'b': 35.91944892145693, 'A': 6.50742934923619, 's': 2.9242282127961516, 't': 2.1714670211076736, 'gamma': 0.1734970062971115}
                             #])

    analysis = tune.run(
        UniTTN,
        metric='test_accuracy',
        mode='max',
        verbose=3,
        num_samples=1,
        config={'num_anc': num_anc,
                'deph_p': deph_p,
                'tune_lr': tune.grid_search([0.015]), #0, # not used in spsa
                'tune_init_std': tune.grid_search([0.5, 0.3, 0.1, 0.07, 0.05, 0.03, 0.01, 0.005]), #0.5, 0.3,
                # 'a': tune.uniform(1, 50),
                # 'b': tune.uniform(1, 50),
                # 'A': tune.uniform(1, 10),
                # 's': tune.uniform(0, 5),
                # 't': tune.uniform(0, 3),
                # 'gamma': tune.uniform(0, 1)
                },
        local_dir='~/ray_results/',
        resources_per_trial={'cpu': 12, 'gpu': 1},
        scheduler=asha_scheduler,
        progress_reporter=tune.CLIReporter(max_progress_rows=100, max_report_frequency=10),
        #search_alg=ax_search,
        log_to_file=False,
        name='anc%.0f_deph%.0f' % (num_anc, deph_p)
    )

    print("Best hyperparameters found were: ", analysis.best_config)
