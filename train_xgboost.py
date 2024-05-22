from dask import array as da
from dask.distributed import Client

from contextlib import contextmanager

import xgboost as xgb
from xgboost import dask as dxgb

from colossus.cosmology import cosmology    
from sklearn.metrics import classification_report
import pickle
import time
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import h5py
import json
import re
from pairing import depair

from utils.data_and_loading_functions import create_directory, load_or_pickle_SPARTA_data, conv_halo_id_spid
##################################################################################################################
# LOAD CONFIG PARAMETERS
import configparser
config = configparser.ConfigParser()
config.read(os.environ.get('PWD') + "/config.ini")
rand_seed = config.getint("MISC","random_seed")
on_zaratan = config.getboolean("MISC","on_zaratan")
curr_sparta_file = config["MISC"]["curr_sparta_file"]
path_to_MLOIS = config["PATHS"]["path_to_MLOIS"]
path_to_snaps = config["PATHS"]["path_to_snaps"]
path_to_SPARTA_data = config["PATHS"]["path_to_SPARTA_data"]
path_to_hdf5_file = path_to_SPARTA_data + curr_sparta_file + ".hdf5"
path_to_pickle = config["PATHS"]["path_to_pickle"]
path_to_calc_info = config["PATHS"]["path_to_calc_info"]
path_to_pygadgetreader = config["PATHS"]["path_to_pygadgetreader"]
path_to_sparta = config["PATHS"]["path_to_sparta"]
path_to_xgboost = config["PATHS"]["path_to_xgboost"]

snap_format = config["MISC"]["snap_format"]
global prim_only
prim_only = config.getboolean("SEARCH","prim_only")
t_dyn_step = config.getfloat("SEARCH","t_dyn_step")
p_red_shift = config.getfloat("SEARCH","p_red_shift")
model_sims = json.loads(config.get("DATASET","model_sims"))

model_type = config["XGBOOST"]["model_type"]
radii_splits = config.get("XGBOOST","rad_splits").split(',')
search_rad = config.getfloat("SEARCH","search_rad")
total_num_snaps = config.getint("SEARCH","total_num_snaps")
per_n_halo_per_split = config.getfloat("SEARCH","per_n_halo_per_split")
test_halos_ratio = config.getfloat("DATASET","test_halos_ratio")
curr_chunk_size = config.getint("SEARCH","chunk_size")
global num_save_ptl_params
num_save_ptl_params = config.getint("SEARCH","num_save_ptl_params")
do_hpo = config.getboolean("XGBOOST","hpo")
frac_training_data = config.getfloat("XGBOOST","frac_train_data")
# size float32 is 4 bytes
chunk_size = int(np.floor(1e9 / (num_save_ptl_params * 4)))
eval_datasets = json.loads(config.get("XGBOOST","eval_datasets"))

from utils.visualization_functions import *
from utils.ML_support import *

import subprocess

try:
    subprocess.check_output('nvidia-smi')
    gpu_use = True
except Exception: # this command not being found can raise quite a few different errors depending on the configuration
    gpu_use = False

if on_zaratan:
    from dask_mpi import initialize
    from mpi4py import MPI
    from distributed.scheduler import logger
    import socket
    #from dask_jobqueue import SLURMCluster
else:
    from dask_cuda import LocalCUDACluster
    from cuml.metrics.accuracy import accuracy_score #TODO fix cupy installation??
    from sklearn.metrics import make_scorer
    import dask_ml.model_selection as dcv
###############################################################################################################
sys.path.insert(0, path_to_pygadgetreader)
sys.path.insert(0, path_to_sparta)
from pygadgetreader import readsnap, readheader
from sparta_tools import sparta
@contextmanager
def timed(txt):
    t0 = time.time()
    yield
    t1 = time.time()
    print("%32s time:  %8.5f" % (txt, t1 - t0))

def get_CUDA_cluster():
    cluster = LocalCUDACluster(
                               device_memory_limit='10GB',
                               jit_unspill=True)
    client = Client(cluster)
    return client

def accuracy_score_wrapper(y, y_hat): 
    y = y.astype("float32") 
    return accuracy_score(y, y_hat, convert_dtype=True)

def do_HPO(model, gridsearch_params, scorer, X, y, mode='gpu-Grid', n_iter=10):
    if mode == 'gpu-grid':
        clf = dcv.GridSearchCV(model,
                               gridsearch_params,
                               cv=N_FOLDS,
                               scoring=scorer)
    elif mode == 'gpu-random':
        clf = dcv.RandomizedSearchCV(model,
                               gridsearch_params,
                               cv=N_FOLDS,
                               scoring=scorer,
                               n_iter=n_iter)

    else:
        print("Unknown Option, please choose one of [gpu-grid, gpu-random]")
        return None, None
    res = clf.fit(X, y,eval_metric='rmse')
    print("Best clf and score {} {}\n---\n".format(res.best_estimator_, res.best_score_))
    return res.best_estimator_, res

def print_acc(model, X_train, y_train, X_test, y_test, mode_str="Default"):
    """
        Trains a model on the train data provided, and prints the accuracy of the trained model.
        mode_str: User specifies what model it is to print the value
    """
    y_pred = model.fit(X_train, y_train).predict(X_test)
    score = accuracy_score(y_pred, y_test.astype('float32'), convert_dtype=True)
    print("{} model accuracy: {}".format(mode_str, score))

if __name__ == "__main__":
    if on_zaratan:
        if 'SLURM_CPUS_PER_TASK' in os.environ:
            cpus_per_task = int(os.environ['SLURM_CPUS_PER_TASK'])
        else:
            print("SLURM_CPUS_PER_TASK is not defined.")
        if gpu_use:
            initialize(local_directory = "/home/zvladimi/scratch/MLOIS/dask_logs/")
        else:
            initialize(nthreads = cpus_per_task, local_directory = "/home/zvladimi/scratch/MLOIS/dask_logs/")
        print("Initialized")
        client = Client()
        host = client.run_on_scheduler(socket.gethostname)
        port = client.scheduler_info()['services']['dashboard']
        login_node_address = "zvladimi@login.zaratan.umd.edu" # Change this to the address/domain of your login node

        logger.info(f"ssh -N -L {port}:{host}:{port} {login_node_address}")
    else:
        client = get_CUDA_cluster()
        
        
    combined_name = ""
    for i,sim in enumerate(model_sims):
        pattern = r"(\d+)to(\d+)"
        match = re.search(pattern, sim)

        if match:
            curr_snap_list = [match.group(1), match.group(2)] 
            print(f"First number: {match.group(1)}")
            print(f"Second number: {match.group(2)}")
        else:
            print("Pattern not found in the string.")
        parts = sim.split("_")
        combined_name += parts[1] + parts[2] + "s" + parts[4] 
        if i != len(model_sims)-1:
            combined_name += "_"
        
    model_name = model_type + "_" + combined_name

    dataset_loc = path_to_xgboost + combined_name + "/datasets/"
    model_save_loc = path_to_xgboost + combined_name + "/" + model_name + "/"
    
    gen_plot_save_loc = model_save_loc + "plots/"
    create_directory(model_save_loc)
    create_directory(gen_plot_save_loc)
    
    train_dataset_loc = dataset_loc + "train_dataset/dataset.pickle"
    train_labels_loc = dataset_loc + "train_dataset/labels.pickle"
    test_dataset_loc = dataset_loc + "test_dataset/dataset.pickle"
    test_labels_loc = dataset_loc + "test_dataset/labels.pickle"
    #TODO condense this in the code to use the same keys
    train_keys_loc = dataset_loc + "train_dataset/keys.pickle"
    test_keys_loc = dataset_loc + "train_dataset/keys.pickle"
     
    if os.path.isfile(model_save_loc + "model_info.pickle"):
        with open(model_save_loc + "model_info.pickle", "rb") as pickle_file:
            model_info = pickle.load(pickle_file)
    else:
        train_sims = ""
        for i,sim in enumerate(model_sims):
            if i != len(model_sims) - 1:
                train_sims += sim + ", "
            else:
                train_sims += sim
        model_info = {
            'Misc Info':{
                'Model trained on': train_sims,
                'Max Radius': search_rad,
                }}
    

    if os.path.isfile(model_save_loc + model_name + ".json"):
        bst = xgb.Booster()
        bst.load_model(model_save_loc + model_name + ".json")
        params = model_info.get('Training Info',{}).get('Training Params')
        print("Loaded Booster")
    else:
        print("Training Set:")
        with open(train_dataset_loc, "rb") as file:
            train_X = pickle.load(file) 
        with open(train_labels_loc, "rb") as file:
            train_y = pickle.load(file)
        with open(train_keys_loc, "rb") as file:
            train_features = pickle.load(file)
        train_features = train_features.tolist()

        dtrain,X_train,y_train,scale_pos_weight = create_dmatrix(client, train_X, train_y, train_features, chunk_size=chunk_size, frac_use_data=frac_training_data, calc_scale_pos_weight=True)
        del train_X
        del train_y
        del train_features
        
        print("Testing set:")
        with open(test_dataset_loc, "rb") as file:
            test_X = pickle.load(file) 
        with open(test_labels_loc, "rb") as file:
            test_y = pickle.load(file)
        with open(test_keys_loc, "rb") as file:
            test_features = pickle.load(file)
        test_features = test_features.tolist()
        dtest,X_test,y_test = create_dmatrix(client, test_X, test_y, test_features, chunk_size=chunk_size, frac_use_data=1, calc_scale_pos_weight=False)
        del test_X
        del test_y
        del test_features
        print("scale_pos_weight:", scale_pos_weight)
        
        if on_zaratan == False and do_hpo == True and os.path.isfile(model_save_loc + "used_params.pickle") == False:  
            params = {
            # Parameters that we are going to tune.
            'max_depth':np.arange(2,4,1),
            # 'min_child_weight': 1,
            'learning_rate':np.arange(0.01,1.01,.1),
            'scale_pos_weight':np.arange(scale_pos_weight,scale_pos_weight+10,1),
            'lambda':np.arange(0,3,.5),
            'alpha':np.arange(0,3,.5),
            'subsample': 0.5,
            # 'colsample_bytree': 1,
            }
        
            N_FOLDS = 5
            N_ITER = 25
            
            model = dxgb.XGBClassifier(tree_method='hist', device="cuda", eval_metric="logloss", n_estimators=100, use_label_encoder=False, scale_pos_weight=scale_pos_weight)
            accuracy_wrapper_scorer = make_scorer(accuracy_score_wrapper)
            cuml_accuracy_scorer = make_scorer(accuracy_score, convert_dtype=True)
            print_acc(model, X_train, y_train, X_test, y_test)
            
            mode = "gpu-random"
            #TODO fix so it takes from model_info.pickle
            if os.path.isfile(model_save_loc + "hyper_param_res.pickle") and os.path.isfile(model_save_loc + "hyper_param_results.pickle"):
                with open(model_save_loc + "hyper_param_res.pickle", "rb") as pickle_file:
                    res = pickle.load(pickle_file)
                with open(model_save_loc + "hyper_param_results.pickle", "rb") as pickle_file:
                    results = pickle.load(pickle_file)
            else:
                with timed("XGB-"+mode):
                    res, results = do_HPO(model,
                                            params,
                                            cuml_accuracy_scorer,
                                            X_train,
                                            y_train,
                                            mode=mode,
                                            n_iter=N_ITER)
                with open(model_save_loc + "hyper_param_res.pickle", "wb") as pickle_file:
                    pickle.dump(res, pickle_file)
                with open(model_save_loc + "hyper_param_results.pickle", "wb") as pickle_file:
                    pickle.dump(results, pickle_file)
                    
                print("Searched over {} parameters".format(len(results.cv_results_['mean_test_score'])))
                print_acc(res, X_train, y_train, X_test, y_test, mode_str=mode)
                print("Best params", results.best_params_)
                
                params = results.best_params_
                
                model_info['Training Info']={
                'Fraction of Training Data Used': frac_training_data,
                'Trained on GPU': gpu_use,
                'HPO used': do_hpo,
                'Training Params': params,
                }            
                
        elif 'Training Info' in model_info: 
            params = model_info.get('Training Info',{}).get('Training Params')
        else:
            params = {
                "verbosity": 1,
                "tree_method": "hist",
                # Golden line for GPU training
                "scale_pos_weight":scale_pos_weight,
                "device": "cuda",
                "subsample": 0.5,
                }
            model_info['Training Info']={
                'Fraction of Training Data Used': frac_training_data,
                'Training Params': params}
            
        print("Starting train using params:", params)
        output = dxgb.train(
            client,
            params,
            dtrain,
            num_boost_round=100,
            evals=[(dtrain, "train"), (dtest,"test")],
            early_stopping_rounds=10,            
            )
        bst = output["booster"]
        history = output["history"]
        bst.save_model(model_save_loc + model_name + ".json")

        plt.figure(figsize=(10,7))
        plt.plot(history["train"]["rmse"], label="Training loss")
        plt.plot(history["test"]["rmse"], label="Validation loss")
        plt.axvline(21, color="gray", label="Optimal tree number")
        plt.xlabel("Number of trees")
        plt.ylabel("Loss")
        plt.legend()
        plt.savefig(gen_plot_save_loc + "training_loss_graph.png")
    
        del dtrain
        del dtest


    for dst_type in eval_datasets:
        with timed(dst_type + " Plots"):
            plot_loc = model_save_loc + dst_type + "_" + combined_name + "/plots/"
            create_directory(model_save_loc + dst_type + combined_name)
            create_directory(plot_loc)
            eval_model(model_info, client, bst, use_sims=model_sims, dst_type=dst_type, dst_loc=dataset_loc, combined_name=combined_name, plot_save_loc=plot_loc, p_red_shift=p_red_shift, dens_prf = True, r_rv_tv = True, misclass=True)
   
    bst.save_model(model_save_loc + model_name + ".json")

    feature_important = bst.get_score(importance_type='weight')
    keys = list(feature_important.keys())
    values = list(feature_important.values())
    pos = np.arange(len(keys))

    fig, ax = plt.subplots(1, figsize=(15,10))
    ax.barh(pos,values)
    ax.set_yticks(pos, keys)
    fig.savefig(gen_plot_save_loc + "feature_importance.png")

    # tree_num = 2
    # xgb.plot_tree(bst, num_trees=tree_num)
    # fig = plt.gcf()
    # fig.set_size_inches(110, 25)
    # fig.savefig('/home/zvladimi/MLOIS/Random_figures/' + model_name + 'tree' + str(tree_num) + '.png')

    with open(model_save_loc + "model_info.pickle", "wb") as pickle_file:
        pickle.dump(model_info, pickle_file) 
    client.close()