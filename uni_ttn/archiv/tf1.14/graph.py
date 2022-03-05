import numpy as np
import tensorflow as tf
import itertools as itr
import model

np.random.seed(45)
tf.random.set_random_seed(45)

'''
This version of the code if a simplified version of graph_original, in which the ancilla part, the various optimizers/losses,
the change of virtual bond dimensions and possibly more are removed.
'''

class Graph:
    def __init__(self, num_pixels, bd_dims, deph, deph_only_input, num_anc, batch_size, config):
        self.bd_dims = bd_dims
        self.num_anc = num_anc
        self.create_op_shapes()
        self.num_op_params = max(self.vir_bd_dim, self.data_bd_dim) ** (self.num_in_bd * 2)
        self.num_pixels = num_pixels
        self.deph = deph
        self.deph_only_input = deph_only_input
        self.config = config
        self.batch_size = batch_size

        self.data_nodes = self.create_data_layer()
        self.num_layers = int(np.log2(self.num_pixels))

        self.op_layers = self.create_all_op_nodes()
        self.create_params_var()

        self.root_node = self.op_layers[self.num_layers - 1][0]
        # self.pred_batch = tf.real(tf.matrix_diag_part(self.root_node.output)) # either works fine
        self.pred_batch = tf.abs(tf.matrix_diag_part(self.root_node.output))
        self.label_batch = tf.placeholder(tf.float32, shape=(None, 2))
        self.optimizer()

        self.init = tf.global_variables_initializer()

    def create_op_shapes(self):
        (self.data_bd_dim, self.vir_bd_dim) = self.bd_dims
        self.num_in_bd = 2 + self.num_anc
        self.fir_lay_op_shape = [self.data_bd_dim] * self.num_in_bd + [self.vir_bd_dim] * self.num_in_bd
        self.mid_lay_op_shape = [self.vir_bd_dim] * (self.num_in_bd * 2)
        self.last_lay_op_shape = [self.vir_bd_dim] * self.num_in_bd + [2] * self.num_in_bd
        self.op_shapes = [self.fir_lay_op_shape, self.mid_lay_op_shape, self.last_lay_op_shape]

    def create_data_layer(self):
        data_nodes = []
        for pixel in range(self.num_pixels):
            node = Data_Node(self.batch_size, self.data_bd_dim)
            data_nodes.append(node)

        return data_nodes

    def create_all_op_nodes(self):
        op_layers = {}
        op_layers[0] = self.create_op_layer(self.data_nodes, 0)
        for lay_ind in range(1, self.num_layers):
            prev_layer = op_layers[lay_ind - 1]
            op_layers[lay_ind] = self.create_op_layer(prev_layer, lay_ind)

        return op_layers

    def create_op_layer(self, prev_layer, lay_ind):
        op_layer = []
        for i in range(0, len(prev_layer), 2):
            input_nodes = (prev_layer[i], prev_layer[i + 1])
            op_node = Op_Node(input_nodes, lay_ind, self.num_layers, self.op_shapes, self.deph,
                              self.deph_only_input, self.num_in_bd, self.num_anc, self.config)
            op_layer.append(op_node)

        return op_layer

    def create_params_var(self):
        op_layers = self.op_layers.values()
        self.op_nodes = list(itr.chain.from_iterable(op_layers))

        self.opt_config = self.config['tree']['opt']
        self.init_mean = self.config['tree']['param']['init_mean']
        self.init_std = self.config['tree']['param']['init_std']

        self.param_var_all = tf.get_variable(
            'param_var_all',
            shape=[self.num_op_params * len(self.op_nodes)],
            dtype=tf.float32,
            initializer=tf.random_normal_initializer(
                mean=self.init_mean, stddev=self.init_std), trainable=True)
        # self.param_var_all = tf.Variable(tf.cast(tf.fill([self.num_op_params * len(self.op_nodes)], 1), tf.float32),
        #     name='param_var_all',
        #     shape=[self.num_op_params * len(self.op_nodes)],
        #     dtype=tf.float32,
        #     )

        for (ind, op_node) in enumerate(self.op_nodes):
            op_node.create_node_tensor(ind, self.param_var_all)

    def optimizer(self):
        self.loss = tf.losses.log_loss(self.label_batch, self.pred_batch); print('Log Loss')    # equivalent to CCE, checked
        # self.loss = tf.keras.losses.CategoricalCrossentropy()(self.label_batch, self.pred_batch)

        opt = tf.train.AdamOptimizer()
        self.grad_var = opt.compute_gradients(self.loss)
        self.train_op = opt.apply_gradients(self.grad_var)
        print('Adam Optimizer', flush=True)

    def run_graph(self, sess, image_batch):
        fd_dict = self.create_pixel_dict(image_batch)
        pred_batch = sess.run(self.pred_batch, feed_dict=fd_dict)
        return pred_batch

    def create_pixel_dict(self, image_batch):
        # if self.config['data']['data_im_size'] == [8, 8]:
        #     pixel_dict = {}
        #     for (index, node) in enumerate(self.data_nodes):
        #         quad = index // 16
        #         quad_quad = (index % 16) // 4
        #         pos = index % 4
        #         row = (pos // 2) + 2 * (quad_quad // 2) + 4 * (quad // 2)
        #         col = (pos % 2) + 2 * (quad_quad % 2) + 4 * (quad % 2)
        #         pixel = col + 8 * row
        #         pixel_dict[node.pixel_batch] = image_batch[:, pixel, :]
        # else:
        pixel_dict = {
            node.pixel_batch: image_batch[:, pixel, :] for (pixel, node) in enumerate(self.data_nodes)}

        return pixel_dict

    def train(self, sess, image_batch, label_batch):
        fd_dict = self.create_pixel_dict(image_batch)
        fd_dict.update({self.label_batch: label_batch})

        if self.opt_config['adam']['show_grad']:
            self.loss_ = float(sess.run(self.loss, feed_dict=fd_dict))

            self.avg_grad = round(float(np.mean(sess.run(self.grad_var[0][0], feed_dict=fd_dict))), 8)
            self.std_grad = round(float(np.std(sess.run(self.grad_var[0][0], feed_dict=fd_dict))), 8)

            self.pred_batch_ = sess.run(self.pred_batch, feed_dict=fd_dict)
            self.label_batch_ = sess.run(self.label_batch, feed_dict=fd_dict)
            check = sess.run(tf.keras.losses.CategoricalCrossentropy()(self.label_batch, self.pred_batch), feed_dict=fd_dict)
            self.root_node.output_ = sess.run(self.root_node.output, feed_dict=fd_dict)
            self.all_grads = sess.run(self.grad_var[0][0], feed_dict=fd_dict)

        sess.run(self.train_op, feed_dict=fd_dict)


class Data_Node:
    def __init__(self, batch_size, data_bd_dim):
        self.data_bd_dim = data_bd_dim
        self.batch_size = batch_size
        self.pixel_batch = tf.placeholder(tf.complex64, shape=(None, self.data_bd_dim))
        conj_pixel_batch = tf.conj(self.pixel_batch)  # not necessary, self.pixel_batch is real
        # conj_pixel_batch = self.pixel_batch
        self.output = tf.einsum('za, zb -> zab', self.pixel_batch, conj_pixel_batch)


def get_mat_shapes(op_shape):
    num_input = len(op_shape) / 2
    mat_shape = [int(op_shape[-1] ** num_input), int(op_shape[0] ** num_input)]
    return mat_shape


def dephase(rho, p=1):
    # this is only true for complete dephasing. Maybe, if this is always acting on a qubit then we are fine with any p
    dephased_rho = (1 - p) * rho + p * tf.matrix_diag(tf.matrix_diag_part(rho))
    return dephased_rho


class Op_Node:
    def __init__(self, input_nodes, lay_ind, num_layers,
                 op_shapes, deph, deph_only_input, num_in_bd, num_anc, config):
        self.input_nodes = input_nodes
        self.lay_ind = lay_ind
        self.num_layers = num_layers
        (self.fir_lay_op_shape, self.mid_lay_op_shape, self.last_lay_op_shape) = op_shapes
        self.fir_lay_mat_shape = get_mat_shapes(self.fir_lay_op_shape)
        self.last_lay_mat_shape = get_mat_shapes(self.last_lay_op_shape)

        self.op_size = self.mid_lay_op_shape[0] ** num_in_bd
        self.max_op_size = self.op_size

        self.deph = deph
        self.deph_only_input = deph_only_input
        self.num_anc = num_anc
        self.config = config

    def create_node_tensor(self, index, param_var):
        self.index = index
        with tf.variable_scope(str(index)):
            self.set_matrix_params(param_var, self.op_size, self.max_op_size)
            self.create_hermitian_matrix(self.op_size)
            unitary_matrix_raw = self.create_unitary_matrix()
            self.create_unitary_tensor(unitary_matrix_raw)
            self.create_contractions()

    def set_matrix_params(self, param_var, op_size, max_op_size):
        num_diags = op_size
        num_off_diags = int(0.5 * op_size * (op_size - 1))
        max_total_params = max_op_size ** 2
        start_slice = self.index * max_total_params
        diag_end = start_slice + num_diags
        real_end = diag_end + num_off_diags
        self.diag_params = tf.slice(param_var, [start_slice], [num_diags])
        self.real_off_params = tf.slice(param_var, [diag_end], [num_off_diags])
        self.imag_off_params = tf.slice(param_var, [real_end], [num_off_diags])

    def create_hermitian_matrix(self, op_size):
        herm_shape = (op_size, op_size)
        diag_part = tf.diag(self.diag_params)
        off_diag_indices = [(i, j) for i in range(op_size) for j in range(i + 1, op_size)]
        real_off_diag_part = tf.scatter_nd(
            indices=off_diag_indices,
            updates=self.real_off_params,
            shape=herm_shape)
        imag_off_diag_part = tf.scatter_nd(
            indices=off_diag_indices,
            updates=self.imag_off_params,
            shape=herm_shape)
        imag_whole = imag_off_diag_part - tf.transpose(imag_off_diag_part)
        real_whole = diag_part + real_off_diag_part + tf.transpose(real_off_diag_part)
        self.herm_matrix = tf.complex(real_whole, imag_whole)

    def create_unitary_matrix(self):
        (eigenvalues, eigenvectors) = tf.linalg.eigh(self.herm_matrix)
        eig_exp = tf.exp(1j * eigenvalues)
        diag_exp_mat = tf.diag(eig_exp)
        unitary_matrix_raw = tf.einsum(
            'ab, bc, dc -> ad',
            eigenvectors,
            diag_exp_mat,
            tf.conj(eigenvectors))

        return unitary_matrix_raw

    def create_unitary_tensor(self, unitary_matrix_raw):
        if self.lay_ind == 0:
            self.unitary_tensor = tf.reshape(
                # tf.transpose(unitary_matrix_raw), # not necessary, but still unitary
                unitary_matrix_raw,
                self.fir_lay_op_shape
            )
            self.op_shape = self.fir_lay_op_shape
        elif self.lay_ind == (self.num_layers - 1):
            self.unitary_tensor = tf.reshape(
                # tf.transpose(unitary_matrix_raw),
                unitary_matrix_raw,
                self.last_lay_op_shape
            )
            self.op_shape = self.last_lay_op_shape
        else:
            self.unitary_tensor = tf.reshape(unitary_matrix_raw, self.mid_lay_op_shape)
            self.op_shape = self.mid_lay_op_shape

    def create_contractions(self):
        (left_node, right_node) = self.input_nodes
        left_input = dephase(left_node.output, 0)
        right_input = dephase(right_node.output, 0)

        # either should work

        # contract_left = tf.einsum('abcd, zea -> zebcd', self.unitary_tensor, left_input)
        # contract_right = tf.einsum('zebcd, zfb -> zefcd', contract_left, right_input)
        # self.output = tf.einsum('zefcd, efcg -> zgd', contract_right, tf.conj(self.unitary_tensor))

        contract_left = tf.einsum('abcd, zce -> zabed', self.unitary_tensor, left_input)
        contract_right = tf.einsum('zabed, zdf -> zabef', contract_left, right_input)
        self.output = tf.einsum('zabef, agef -> zbg', contract_right, tf.conj(self.unitary_tensor))
