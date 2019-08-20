# coding=utf-8

import matplotlib.pyplot as plt
import numpy as np
from keras.models import Sequential, load_model
from keras.layers import Conv2D, MaxPooling2D, UpSampling2D, BatchNormalization, Reshape, Permute, Activation, Input
from keras.utils.np_utils import to_categorical
from keras.preprocessing.image import img_to_array
from keras.callbacks import ModelCheckpoint, EarlyStopping, History, ReduceLROnPlateau
from keras.models import Model
from keras.layers.merge import concatenate
import matplotlib.pyplot as plt
import cv2
import random
import sys
import os
import time
from tqdm import tqdm
from keras.models import *
from keras.layers import *
from keras.optimizers import *
from keras.models import load_model

from keras import backend as K

K.set_image_dim_ordering('tf')
from keras.callbacks import TensorBoard
from keras.utils import multi_gpu_model


from ulitities.base_functions import load_img_normalization, load_img_normalization_bybandlist, load_img_by_gdal, \
    UINT16, UINT8, UINT10

seed = 4
np.random.seed(seed)
from keras import metrics, losses
from keras.losses import binary_crossentropy
from segmentation_models.losses import *
from segmentation_models.metrics import iou_score
from segmentation_models.losses import self_define_loss, bce, cce

from segmentation_models import Unet, FPN, PSPNet, Linknet
from segmentation_models.deeplab.model import Deeplabv3

from utils import save, update_config
from config import Config
import json
import sys
from ulitities.base_functions import get_file, get_file_absname
from keras.utils import plot_model
import argparse

parser = argparse.ArgumentParser(description='RS classification train')
parser.add_argument('--gpu', dest='gpu_id', help='GPU device id to be used ', nargs='+',
                    default=0, type=int)
parser.add_argument('--config', dest='config_file', help='json file to config',
                    default='config_scrs_buildings_original.json')
args = parser.parse_args()
gpu_id = args.gpu_id
print("gpu_id:{}".format(gpu_id))
# os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
if isinstance(gpu_id, int):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
elif isinstance(gpu_id, list):
    tp_str = []
    for i in gpu_id:
        tp_str.append(str(i))
    ns = ",".join(tp_str)
    os.environ["CUDA_VISIBLE_DEVICES"] = ns
else:
    pass

with open(args.config_file, 'r') as f:
    cfg = json.load(f)

config = Config(**cfg)
print(config)

FLAG_MAKE_TEST = True
im_type = UINT8
if '10' in config.im_type:
    im_type = UINT10
elif '16' in config.im_type:
    im_type = UINT16
else:
    pass

date_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
print("date and time: {}".format(date_time))
print("traindata from: {}".format(config.train_data_path))
band_name = ''
if len(config.band_list) == 0:
    band_name = 'fullbands'
else:
    for i in range(len(config.band_list)):
        band_name += str(config.band_list[i])
    band_name += "bands"
print("band_name:{}".format(band_name))
model_save_path = ''.join(
    [config.model_dir, '/', config.target_name, '_', config.network, '_', config.BACKBONE, '_', config.loss, '_',
     config.optimizer, '_', str(config.img_w), '_', band_name, '_', date_time, 'best.h5'])
print("model save as to: {}".format(model_save_path))
last_model = ''.join(
    [config.model_dir, '/', config.target_name, '_', config.network, '_', config.BACKBONE, '_', config.loss, '_',
     config.optimizer, '_', str(config.img_w), '_', band_name, '_', date_time, 'last.h5'])

# trainset_dir = config.train_data_path + 'train/'
# if not os.path.isdir(trainset_dir):
#     print("train set directory is not existed!")
#     sys.exit(-1)
# valset_dir = config.train_data_path + 'val/'
# if not os.path.isdir(valset_dir):
#     print("validation set directory is not existed!")
#     sys.exit(-1)


"""get the train file name and divide to train and val parts"""
def get_train_val(val_rate=config.val_rate):
    train_url = []
    train_set = []
    val_set = []
    for pic in os.listdir(config.train_data_path + 'label'):
        train_url.append(pic)
    random.shuffle(train_url)
    total_num = len(train_url)
    val_num = int(val_rate * total_num)
    for i in range(len(train_url)):
        if i < val_num:
            val_set.append(train_url[i])
        else:
            train_set.append(train_url[i])
    return train_set, val_set

# data for training
def generateData(config, data=[]):
    # print 'generateData...'
    while True:
        train_data = []
        train_label = []
        batch = 0
        for i in (range(len(data))):
            url = data[i]
            batch += 1

            try:
                _, img = load_img_normalization_bybandlist((trainset_dir + '/src/' + url), bandlist=config.band_list,
                                                           data_type=im_type)
            except RuntimeError:
                raise RuntimeError("Open file faild:{}".format(url))

            # Adapt dim_ordering automatically
            img = img_to_array(img)
            train_data.append(img)
            _, label = load_img_normalization(1, (trainset_dir + '/label/' + url))
            label = img_to_array(label)
            train_label.append(label)
            if batch % config.batch_size == 0:
                # print 'get enough bacth!\n'
                train_data = np.array(train_data)
                train_label = np.array(train_label)
                if config.nb_classes > 2:
                    train_label = to_categorical(train_label, num_classes=config.nb_classes)
                # train_label = train_label.reshape((config.batch_size, config.img_w * config.img_h,config.nb_classes))
                # print("train_label shape:{}".format(train_label.shape))

                yield (train_data, train_label)
                train_data = []
                train_label = []
                batch = 0


# data for validation
def generateValidData(config, data=[]):
    # print 'generateValidData...'
    while True:
        valid_data = []
        valid_label = []
        batch = 0
        for i in (range(len(data))):
            url = data[i]
            batch += 1
            try:
                _, img = load_img_normalization_bybandlist((valset_dir + '/src/' + url), bandlist=config.band_list,
                                                           data_type=im_type)
            except RuntimeError:
                raise RuntimeError("Open file faild:{}".format(url))
            # Adapt dim_ordering automatically
            img = img_to_array(img)
            valid_data.append(img)
            _, label = load_img_normalization(1, (valset_dir + '/label/' + url))
            label = img_to_array(label)
            valid_label.append(label)
            if batch % config.batch_size == 0:
                valid_data = np.array(valid_data)
                valid_label = np.array(valid_label)
                if config.nb_classes > 2:
                    valid_label = to_categorical(valid_label, num_classes=config.nb_classes)
                # valid_label = valid_label.reshape((config.batch_size, config.img_w * config.img_h,config.nb_classes))
                yield (valid_data, valid_label)
                valid_data = []
                valid_label = []
                batch = 0


def transfer_weights(trained_backbone, model):
    for i, layer in enumerate(trained_backbone.layers):
        weights = layer.get_weights()
        model.layers[i].set_weights(weights)


"""Train model ............................................."""


def train(model):
    if os.path.isfile(config.base_model):
        try:
            model.load_weights(config.base_model)
        except ValueError:
            print("Can not load weights from base model: {}".format(config.base_model))
        else:
            print("loaded weights from base model:{}".format(config.base_model))

    model_checkpoint = ModelCheckpoint(
        model_save_path,
        monitor=config.monitor,
        save_best_only=config.save_best_only,
        mode=config.mode
    )

    model_earlystop = EarlyStopping(
        monitor=config.monitor,
        patience=config.patience + 5,
        verbose=0,
        mode=config.mode
    )

    # """自动调整学习率"""
    model_reduceLR = ReduceLROnPlateau(
        monitor=config.monitor,
        factor=config.factor,
        patience=config.patience,
        verbose=0,
        mode=config.mode,
        epsilon=config.epsilon,
        cooldown=config.cooldown,
        min_lr=config.min_lr
    )

    model_history = History()

    logdir = ''.join(
        [config.log_dir, '/log', config.target_name, "_", config.network, "_", config.BACKBONE, "_", config.loss,
         date_time])
    if not os.path.isdir(logdir):
        print("Warning: ")
        os.mkdir(logdir)

    tb_log = TensorBoard(log_dir=logdir)

    callable = [model_checkpoint, model_earlystop, model_reduceLR, model_history, tb_log]

    train_set, val_set = get_train_val()
    # train_set = get_file_absname(trainset_dir + 'label')
    # val_set = get_file_absname(valset_dir + 'label')
    train_numb = len(train_set)
    valid_numb = len(val_set)
    print("the number of train data is", train_numb)
    print("the number of val data is", valid_numb)

    if isinstance(gpu_id, int):
        print("using single gpu {}".format(gpu_id))
        pass
    elif isinstance(gpu_id, list):
        print("using multi gpu {}".format(gpu_id))
        if len(gpu_id) > 1:
            model = multi_gpu_model(model, gpus=len(gpu_id))

    self_optimizer = SGD(lr=config.lr, decay=1e-6, momentum=0.9, nesterov=True)
    if 'adagrad' in config.optimizer:
        self_optimizer = Adagrad(lr=config.lr, decay=1e-6)
    elif 'adam' in config.optimizer:
        self_optimizer = Adam(lr=config.lr, decay=1e-6)
    else:
        pass

    model.compile(self_optimizer, loss=config.loss, metrics=[config.metrics])
    print("metrics:{}".format(model.metrics_names))

    model_reduceLR.set_model(model)
    batch_no = train_numb//config.batch_size

    train_data = []
    train_label = []
    batch = 0
    for i in (range(len(train_set))):
        url = train_set[i]
        batch += 1

        try:
            _, img = load_img_normalization_bybandlist((config.train_data_path + '/src/' + url), bandlist=config.band_list,
                                                       data_type=im_type)
        except RuntimeError:
            raise RuntimeError("Open file faild:{}".format(url))

        # Adapt dim_ordering automatically
        img = img_to_array(img)
        train_data.append(img)
        _, label = load_img_normalization(1, (config.train_data_path + '/label/' + url))
        label = img_to_array(label)
        train_label.append(label)
        if batch % config.batch_size == 0:
            # print 'get enough bacth!\n'
            train_data = np.array(train_data)
            train_label = np.array(train_label)
            if config.nb_classes > 2:
                train_label = to_categorical(train_label, num_classes=config.nb_classes)
            # train_label = train_label.reshape((config.batch_size, config.img_w * config.img_h,config.nb_classes))
            # print("train_label shape:{}".format(train_label.shape))

            # yield (train_data, train_label)
            t_loss = model.train_on_batch(train_data, train_label)
            print("{}:{}".format(model.metrics_names, t_loss))
            train_data = []
            train_label = []
            batch = 0


    valid_data = []
    valid_label = []
    batch = 0
    for i in (range(len(val_set))):
        url = val_set[i]
        batch += 1
        try:
            _, img = load_img_normalization_bybandlist((config.train_data_path + '/src/' + url), bandlist=config.band_list,
                                                       data_type=im_type)
        except RuntimeError:
            raise RuntimeError("Open file faild:{}".format(url))
        # Adapt dim_ordering automatically
        img = img_to_array(img)
        valid_data.append(img)
        _, label = load_img_normalization(1, (config.train_data_path + '/label/' + url))
        label = img_to_array(label)
        valid_label.append(label)

        # if batch % config.batch_size == 0:
        #     valid_data = np.array(valid_data)
        #     valid_label = np.array(valid_label)
        #     if config.nb_classes > 2:
        #         valid_label = to_categorical(valid_label, num_classes=config.nb_classes)
        #     # valid_label = valid_label.reshape((config.batch_size, config.img_w * config.img_h,config.nb_classes))
        #     # yield (valid_data, valid_label)
        #
        #     valid_data = []
        #     valid_label = []
        #     batch = 0
    valid_data = np.array(valid_data)
    valid_label = np.array(valid_label)
    if config.nb_classes > 2:
        valid_label = to_categorical(valid_label, num_classes=config.nb_classes)
    val_loss = model.evaluate(valid_data,valid_label, batch_size=8) #something wrong
    print("{}:{}".format(model.metrics_names, val_loss))

    model.save(last_model)


"""
Test the model which has been trained right now
"""
window_size = config.img_w




def add_new_model(base_moldel, cofig):
    x = base_moldel.get_layer('softmax').output
    x = Reshape((config.img_w * config.img_h, config.nb_classes))(x)
    model = Model(input=base_moldel.input, output=x)
    return model


if __name__ == '__main__':

    if not os.path.isdir(config.train_data_path):
        print("train data does not exist in the path:\n {}".format(config.train_data_path))
        sys.exit(-1)

    if len(config.band_list) == 0:
        print("Error: band_list should not be empty!")
        sys.exit(-2)
    input_layer = (config.img_w, config.img_h, len(config.band_list))
    if 'unet' in config.network:
        model = Unet(backbone_name=config.BACKBONE, input_shape=input_layer,
                     classes=config.nb_classes, activation=config.activation,
                     encoder_weights=config.encoder_weights)
    elif 'pspnet' in config.network:
        model = PSPNet(backbone_name=config.BACKBONE, input_shape=input_layer,
                       classes=config.nb_classes, activation=config.activation,
                       encoder_weights=config.encoder_weights)
    elif 'fpn' in config.network:
        model = FPN(backbone_name=config.BACKBONE, input_shape=input_layer,
                    classes=config.nb_classes, activation=config.activation,
                    encoder_weights=config.encoder_weights)
    elif 'linknet' in config.network:
        model = Linknet(backbone_name=config.BACKBONE, input_shape=input_layer,
                        classes=config.nb_classes, activation=config.activation,
                        encoder_weights=config.encoder_weights)
    elif 'deeplabv3plus' in config.network:
        try:
            model = Deeplabv3(weights=config.encoder_weights, input_shape=input_layer,
                              classes=config.nb_classes, backbone=config.BACKBONE, activation=config.activation)
        except RuntimeError:
            print("Warning: Run this model with a backend that does not support separable convolutions.")
            model = Deeplabv3(weights=None, input_shape=input_layer,
                              classes=config.nb_classes, backbone="mobilenetv2", activation=config.activation)
        except ValueError:
            print("Warning:  invalid argument for `weights` or `backbone.")
            model = Deeplabv3(weights=None, input_shape=input_layer,
                              classes=config.nb_classes, backbone="mobilenetv2", activation=config.activation)
        else:
            print("input parameters correct for deeplab V3+!")
        # finally:
        #     print("deeplab model")

    else:
        print("Error:")

    print(model.summary())
    print("Train by : {}_{}".format(config.network, config.BACKBONE))
    # plot_model(model,to_file='model.png')
    # sys.exit(-2)
    #
    # model=add_new_model(model, config)
    # print(model.summary())

    """ Training model........"""
    train(model)
