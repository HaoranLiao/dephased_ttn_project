# Decohering tensor network QML models
## Unitary Tree Tensor Network and MERA

Efficient unitary tree tensor netwokr (TTN) and Multi-scale Entanglement Renormalization Ansatz (MERA) built with Tensorflow, with tunable local dephasing channels at every layer of the tensor networks, benchmarked on compressed MNIST, KMNIST, and Fashion-MNIST.

To setup, 
```
cd dephased_ttn_mera/uni_ttn/tf2/dependency
conda env create -f environment_tf2.7.yaml
conda activate tf2
```

Add this to ```~/.bashrc```:

```export PYTHONPATH="${PYTHONPATH}:HOME_DIR/dephased_ttn_mera/"```

and ```source ~/.bashrc```.

To run, for example, the MERA,
```cd dephased_ttn_mera/mera```.


Configure ```config_example.yaml```, and run
```python model.py```
