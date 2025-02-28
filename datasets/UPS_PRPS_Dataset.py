from __future__ import division
import os
import numpy as np
#from scipy.ndimage import imread
from imageio import imread

import torch
import torch.utils.data as data

from datasets import pms_transforms
from . import util
np.random.seed(0)

class UPS_PRPS_Dataset(data.Dataset):
    def __init__(self, args, root, split='train'):
        self.root  = os.path.join(root)
        self.split = split
        self.args  = args
        self.shape_list = util.readList(os.path.join(self.root, split + args.l_suffix))

    def _getInputPath(self, index):
        shape, mtrl = self.shape_list[index].split('/')
        normal_path = os.path.join(self.root, 'Images', shape, shape + '_normal.png')
        img_dir     = os.path.join(self.root, 'Images', self.shape_list[index])
        img_list    = util.readList(os.path.join(img_dir, '%s_%s.txt' % (shape, mtrl)))

        data = np.genfromtxt(img_list, dtype='str', delimiter=' ')
        select_idx = np.random.permutation(data.shape[0])[:self.args.in_img_num]
        idxs = ['%04d' % (idx) for idx in select_idx]
        data = data[select_idx, :]
        imgs = [os.path.join(img_dir, img) for img in data[:, 0]]
        dirs = data[:, 1:4].astype(np.float32)

        data_all = np.genfromtxt(img_list, dtype='str', delimiter=' ')
        select_idx_all = np.random.permutation(data_all.shape[0])[:1000]
        idxs_all = ['%04d' % (idx) for idx in select_idx_all]
        data_all = data_all[select_idx_all, :]
        imgs_all = [os.path.join(img_dir, img) for img in data_all[:, 0]]
        dirs_all = data_all[:, 1:4].astype(np.float32)
        return normal_path, imgs, dirs, imgs_all, dirs_all

    def __getitem__(self, index):
        normal_path, img_list, dirs, img_all_list, dirs_all = self._getInputPath(index)
        normal = imread(normal_path).astype(np.float32) / 255.0 * 2 - 1
        imgs   =  []
        for i in img_list:
            img = imread(i).astype(np.float32) / 255.0
            imgs.append(img)
        img = np.concatenate(imgs, 2)

        if self.args.stage2:
            imgs_all   =  []
            for i in img_all_list:
                img_all = imread(i).astype(np.float32) / 255.0
                imgs_all.append(img_all)
            img_all = np.concatenate(imgs_all, 2)

        h, w, c = img.shape
        crop_h, crop_w = self.args.crop_h, self.args.crop_w
        if self.args.rescale and not (crop_h == h):
            sc_h = np.random.randint(crop_h, h) if self.args.rand_sc else self.args.scale_h
            sc_w = np.random.randint(crop_w, w) if self.args.rand_sc else self.args.scale_w
            img, normal = pms_transforms.rescale(img, normal, [sc_h, sc_w])
            if self.args.stage2:
                img_all, _ = pms_transforms.rescale(img_all, normal, [sc_h, sc_w])

        if self.args.crop:
            img, normal = pms_transforms.randomCrop(img, normal, [crop_h, crop_w])
            if self.args.stage2:
                img_all, _ = pms_transforms.randomCrop(img_all, normal, [crop_h, crop_w])

        if self.args.color_aug:
            # img = img * np.random.uniform(1, self.args.color_ratio)
            r = np.random.uniform(1, self.args.color_ratio)
            img = img * r
            if self.args.stage2:
                img_all = img_all * r

        if self.args.int_aug:
            ints = pms_transforms.getIntensity(len(imgs))
            img  = np.dot(img, np.diag(ints.reshape(-1)))
            if self.args.stage2:
                img_all  = np.dot(img_all, np.diag(ints.reshape(-1)))
        else:
            ints = np.ones(c)

        if self.args.noise_aug:
            img = pms_transforms.randomNoiseAug(img, self.args.noise)

        mask   = pms_transforms.normalToMask(normal)
        normal = normal * mask.repeat(3, 2) 
        norm   = np.sqrt((normal * normal).sum(2, keepdims=True))
        normal = normal / (norm + 1e-10) # Rescale normal to unit length

        item = {'normal': normal, 'img': img, 'mask': mask}
        for k in item.keys(): 
            item[k] = pms_transforms.arrayToTensor(item[k])

        item['dirs'] = torch.from_numpy(dirs).view(-1, 1, 1).float()
        item['ints'] = torch.from_numpy(ints).view(-1, 1, 1).float()
        if self.args.stage2:
            item['img_all'] = pms_transforms.arrayToTensor(img_all)
            item['dirs_all'] = torch.from_numpy(dirs_all).view(-1, 1, 1).float()
        return item

    def __len__(self):
        return len(self.shape_list)