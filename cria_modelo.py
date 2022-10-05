from numpy import array
import torch
import gc
import torch.nn as nn
from tqdm import tqdm_notebook as tqdm
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import requests, zipfile, io
import matplotlib.pyplot as plt
import os
import seaborn as sns
import sklearn.metrics as skl 
import sklearn.preprocessing as preproc
from torch.utils.data import TensorDataset

from pre_processamento import pre_proc


#-------------------------------------------------- Criação de funções e classes -----------------------------------------------------------------------------------------------------

#Função de Janelamento
def apply_windowing(X, initial_time_step, max_time_step, window_size, idx_target):

  assert idx_target >= 0 and idx_target < X.shape[1]
  assert initial_time_step >= 0
  assert max_time_step >= initial_time_step

  start = initial_time_step
    
  sub_windows = (
        start +
        # expand_dims converts a 1D array to 2D array.
        np.expand_dims(np.arange(window_size), 0) +
        np.expand_dims(np.arange(max_time_step + 1), 0).T
  )
    
  return X[sub_windows], X[window_size:(max_time_step+window_size+1):1, idx_target]

class EarlyStopping:
    """Early stops the training if validation loss doesn't improve after a given patience."""
    def __init__(self, patience=7, verbose=False, delta=0):
        """
        Args:
            patience (int): How long to wait after last time validation loss improved.
                            Default: 7
            verbose (bool): If True, prints a message for each validation loss improvement. 
                            Default: False
            delta (float): Minimum change in the monitored quantity to qualify as an improvement.
                            Default: 0
        """
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = np.Inf
        self.delta = delta

    def __call__(self, val_loss, model):

        score = -val_loss

        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
        elif score < self.best_score + self.delta:
            self.counter += 1
            print(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
            self.counter = 0

    def save_checkpoint(self, val_loss, model):
        '''Saves model when validation loss decrease.'''
        if self.verbose:
            print(f'Validation loss decreased ({self.val_loss_min:.6f} --> {val_loss:.6f}).  Saving model ...')
        torch.save(model.state_dict(), 'checkpoint.pt')
        self.val_loss_min = val_loss

class Net(nn.Module):
    def __init__(self, in_channels):
        super(Net,self).__init__()
        self.conv1d = nn.Conv1d(in_channels = in_channels, out_channels = 64, kernel_size = 2)
        self.relu = nn.ReLU()#inplace = True)
        
        #RuntimeError: mat1 and mat2 shapes cannot be multiplied (32x320 and 128x50)
        #RuntimeError: mat1 and mat2 shapes cannot be multiplied (32x320 and 128x320)
        self.fc1 = nn.Linear(320,50)
        self.fc2 = nn.Linear(50,1)

    def forward(self,x):
        #print('Input: ', x.shape)
        x = self.conv1d(x)
        #print('After conv1: ', x.shape)
        x = self.relu(x)
        #print('After ReLU: ', x.shape)
        x = x.view(x.shape[0], -1)
        #print('After flatenning: ', x.shape)
        x = self.fc1(x)
        #print(x.shape)
        x = self.relu(x)
        x = self.fc2(x)
        #print('return')
        #print(x.shape)
        return x

def fit(epochs, lr, model, train_loader, val_loader,patience, opt_func=torch.optim.SGD):
    
    # to track the training loss as the model trains
    train_losses = []
    # to track the validation loss as the model trains
    valid_losses = []
    # to track the average training loss per epoch as the model trains
    avg_train_losses = []
    # to track the average validation loss per epoch as the model trains
    avg_valid_losses = [] 
    
    optimizer = opt_func(model.parameters(), lr)

    # initialize the early_stopping object
    early_stopping = EarlyStopping(patience=patience, verbose=True)

    for epoch in range(epochs):

        ###################
        # train the model #
        ###################
        model.train() # prep model for training
        for data, target in train_loader:
            # clear the gradients of all optimized variables
            optimizer.zero_grad()
            # forward pass: compute predicted outputs by passing inputs to the model
            output = model(data.float())

            # calculate the loss
            loss = criterion(output, target.float())
            
            # backward pass: compute gradient of the loss with respect to model parameters
            loss.backward()
            # perform a single optimization step (parameter update)
            optimizer.step()
            # record training loss
            train_losses.append(loss.item())

        ######################    
        # validate the model #
        ######################
        model.eval() # prep model for evaluation
        for data, target in val_loader:
            # forward pass: compute predicted outputs by passing inputs to the model
            output = model(data.float())
            # calculate the loss
            loss = criterion(output, target.float())
            # record validation loss
            valid_losses.append(loss.item())

        # print training/validation statistics 
        # calculate average loss over an epoch
        train_loss = np.average(train_losses)
        valid_loss = np.average(valid_losses)
        avg_train_losses.append(train_loss)
        avg_valid_losses.append(valid_loss)
        
        epoch_len = len(str(n_epochs))
        
        print_msg = (f'[{epoch:>{epoch_len}}/{n_epochs:>{epoch_len}}] ' +
                     f'train_loss: {train_loss:.5f} ' +
                     f'valid_loss: {valid_loss:.5f}')
        
        print(print_msg)
        
        # clear lists to track next epoch
        train_losses = []
        valid_losses = []

        early_stopping(valid_loss, model)
        
        if early_stopping.early_stop:
            print("Early stopping")
            break

    return  model, avg_train_losses, avg_valid_losses

#-------------------------------------------------------------------------------------------------------------------------------------------------------

cor_est = ['alto_da_boa_vista','guaratiba','iraja','jardim_botanico','riocentro','santa_cruz','sao_cristovao','vidigal']
arquivo = 'RIO DE JANEIRO - FORTE DE COPACABANA_1997_2022'
log_CAPE = 1

# Pré processamento
df = pre_proc('RIO DE JANEIRO - FORTE DE COPACABANA_1997_2022',1,1,1)
print(df.describe())

if log_CAPE:
    df['CAPE'][0] = 0
    df['CIN'][0] = 0
    df = df.interpolate(method='linear')

# Normalização dos Dados
if arquivo in cor_est:
    df1 = df.drop(columns=['Dia','Hora','estacao'])
else:
    df1 = df.drop(columns=['DC_NOME','UF','DT_MEDICAO','CD_ESTACAO','VL_LATITUDE','VL_LONGITUDE','HR_MEDICAO'])

d_max = df1.max()
d_min = df1.min()
df_norm=(df1-df1.min())/(df1.max()-df1.min())

# Separação dos Dados
n = len(df_norm)
train_df = df_norm[0:int(n*0.7)]
val_df = df_norm[int(n*0.7):int(n*0.9)]
test_df = df_norm[int(n*0.9):]

num_features = df_norm.shape[1]

# Janelamento
train_arr = np.array(train_df)
val_arr = np.array(val_df)
test_arr = np.array(test_df)

# Execução do janelamento
TIME_WINDOW_SIZE = 6    # Espaço de Janelamento
IDX_TARGET = 0          # Variavel a ser predita ( CHUVA )

train_x, train_y = apply_windowing(train_arr, 
                                  initial_time_step=0, 
                                  max_time_step=len(train_arr)-TIME_WINDOW_SIZE-1, 
                                  window_size = TIME_WINDOW_SIZE, 
                                  idx_target = IDX_TARGET)
train_y = train_y.reshape(-1,1)

val_x, val_y = apply_windowing(val_arr, 
                                  initial_time_step=0, 
                                  max_time_step=len(val_arr)-TIME_WINDOW_SIZE-1, 
                                  window_size = TIME_WINDOW_SIZE, 
                                  idx_target = IDX_TARGET)
val_y = val_y.reshape(-1,1)

test_x, test_y = apply_windowing(test_arr, 
                                  initial_time_step=0, 
                                  max_time_step=len(test_arr)-TIME_WINDOW_SIZE-1, 
                                  window_size = TIME_WINDOW_SIZE, 
                                  idx_target = IDX_TARGET)
test_y = test_y.reshape(-1,1)

train_x = torch.from_numpy(train_x.astype('float64'))
train_x = torch.permute(train_x, (0, 2, 1))
train_y = torch.from_numpy(train_y.astype('float64'))

val_x = torch.from_numpy(val_x.astype('float64'))
val_x = torch.permute(val_x, (0, 2, 1))
val_y = torch.from_numpy(val_y.astype('float64'))

test_x = torch.from_numpy(test_x.astype('float64'))
test_x = torch.permute(test_x, (0, 2, 1))
test_y = torch.from_numpy(test_y.astype('float64'))  

train_ds = TensorDataset(train_x, train_y)
val_ds = TensorDataset(val_x, val_y)
test_ds = TensorDataset(test_x, test_y)

BATCH_SIZE = 32
train_loader = torch.utils.data.DataLoader(train_ds, batch_size = BATCH_SIZE, shuffle = False)
val_loader = torch.utils.data.DataLoader(val_ds, batch_size = BATCH_SIZE, shuffle = False)
test_loader = torch.utils.data.DataLoader(test_ds, batch_size = BATCH_SIZE, shuffle = False)

# Gera modelo
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
model = Net(in_channels=28).to(device)

criterion = nn.MSELoss()

# Erro relativo antes do treinamento
test_losses = []
for xb, yb in test_loader:
  output = model(xb.float())
  # calculate the loss
  loss = criterion(output, yb.float())
  # record validation loss
  test_losses.append(loss.item())
test_loss = np.average(test_losses)
print('Perda média pré treinamento: ')  
print(test_loss)

# Treinamento
n_epochs = 500
patience = 10

model = model.float()
model, train_loss, val_loss = fit(n_epochs, 1e-5, model, train_loader, val_loader,patience, opt_func=torch.optim.Adam)

# Erro relativo pós treinamento
test_losses = []
for xb, yb in test_loader:
  output = model(xb.float())
  # calculate the loss
  loss = criterion(output, yb.float())
  # record validation loss
  test_losses.append(loss.item())
test_loss = np.average(test_losses)
print('Perda média pós treinamento: ')  
print(test_loss)

# Gráfico
fig = plt.figure(figsize=(10,8))
plt.plot(range(1,len(train_loss)+1),train_loss, label='Training Loss')
plt.plot(range(1,len(val_loss)+1),val_loss,label='Validation Loss')
plt.xlabel('epochs')
plt.ylabel('loss')
plt.xlim(0, len(train_loss)+1)
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
fig.savefig(arquivo + '_loss_plot.png', bbox_inches='tight')

# Resultados do modelo
test_losses = []
outputs = []
with torch.no_grad():
  for xb, yb in test_loader:
    output = model(xb.float())
    outputs.append(output)
test_predictions = torch.vstack(outputs).squeeze(1)
test_predictions.numpy()
test_predictions = torch.cat((test_predictions, torch.tensor([0,0,0,0,0,0])), 0)

# Resetando os Conjuntos de dados
train_df = df[0:int(n*0.7)]
val_df = df[int(n*0.7):int(n*0.9)]
test_df = df[int(n*0.9):]

if arquivo in cor_est:
    # Erro médio do modelo
    test_predictions = (test_predictions * (d_max['Chuva'] - d_min['Chuva']) + d_min['Chuva'])
    skl.mean_absolute_error(test_df['Chuva'], test_predictions)

    # Visualização do desempenho do modelo
    fig, ax = plt.subplots(1, 1, figsize=(15, 5))
    ax.plot(train_df['Dia'], train_df['Chuva'], lw=2, label='train data')
    ax.plot(val_df['Dia'], val_df['Chuva'], lw=2, label='val data')
    ax.plot(test_df['Dia'], test_df['Chuva'], lw=3, c='y', label='test data')
    ax.plot(test_df['Dia'], test_predictions, lw=3, c='r',linestyle = ':', label='predictions')
    ax.legend(loc="upper left")
    plt.show()
    fig.savefig(arquivo + '_Desempenho_Geral.png', bbox_inches='tight')

    fig, ax = plt.subplots(1, 1, figsize=(15, 5))
    ax.plot(test_df['Dia'], test_df['Chuva'], lw=3, c='y', label='test data')
    ax.plot(test_df['Dia'], test_predictions, lw=3, c='r',linestyle = ':', label='predictions')
    ax.legend(loc="upper left")
    plt.show()
    fig.savefig(arquivo + '_Desempenho_Teste.png', bbox_inches='tight')
else:
    # Erro médio do modelo
    test_predictions = (test_predictions * (d_max['CHUVA'] - d_min['CHUVA']) + d_min['CHUVA'])
    skl.mean_absolute_error(test_df['CHUVA'], test_predictions)
    
    fig, ax = plt.subplots(1, 1, figsize=(15, 5))
    ax.plot(train_df['DT_MEDICAO'], train_df['CHUVA'], lw=2, label='train data')
    ax.plot(val_df['DT_MEDICAO'], val_df['CHUVA'], lw=2, label='val data')
    ax.plot(test_df['DT_MEDICAO'], test_df['CHUVA'], lw=3, c='y', label='test data')
    ax.plot(test_df['DT_MEDICAO'], test_predictions, lw=3, c='r',linestyle = ':', label='predictions')
    ax.legend(loc="upper left")
    plt.show()
    fig.savefig(arquivo + '_Desempenho_Geral.png', bbox_inches='tight')
    
    fig, ax = plt.subplots(1, 1, figsize=(15, 5))
    ax.plot(test_df['DT_MEDICAO'], test_df['CHUVA'], lw=3, c='y', label='test data')
    ax.plot(test_df['DT_MEDICAO'], test_predictions, lw=3, c='r',linestyle = ':', label='predictions')
    ax.legend(loc="upper left")
    plt.show()
    fig.savefig(arquivo + '_Desempenho_Teste.png', bbox_inches='tight')





