import glob
import ast
import os
import sys
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt 
from simple_cnn_v2 import create_model4, create_model2, create_model3, plot_confusion_matrix
from keras.layers import Activation, Convolution2D, Dense, Dropout, Flatten, MaxPooling2D
from keras.models import Sequential
from keras.layers import Input
from keras.models import Model
from keras.preprocessing.image import ImageDataGenerator
from keras.applications.xception import preprocess_input
from keras.callbacks import EarlyStopping
from keras.callbacks import TensorBoard
from keras.callbacks import ModelCheckpoint
from keras.models import load_model
from keras.utils import to_categorical
from sklearn.metrics import confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
from plot_reconstruction import plot_reconstruction
from sklearn.naive_bayes import MultinomialNB
from sklearn import decomposition
from sklearn.ensemble import RandomForestClassifier
from numpy.random import seed
seed(1)
np.set_printoptions(precision=2)

class EmotionFaceClassifier():

    def __init__(self, home, cv2_path, df_path):
        self.home = home
        self.cv2_path = cv2_path
        self.df_path = df_path
        self.df_csv = ''.join([df_path, '.csv'])
        self.df_output_pkl = ''.join([df_path,'_ouput.pkl'])
        self.df_output_csv = ''.join([df_path,'_ouput.csv'])
        self.emo_dict = {0:'Angry', 1:'Disgust', 2: 'Fear', 3:'Happy', 4: 'Sad', 5:'Surprise', 6: 'Neutral'}
        self.emo_list = list(self.emo_dict.values())
        self.results_df = pd.DataFrame()
        self.n_components=10
        self.n_trees = 300
        self.seed_val = 99
        self.min_sample = 547
        self.batch_size = 128
        self.n_epochs = 100
    
    def run_analysis(self):
        self.load_data()
        self.save_df()
        self.plot_example_images()
        self.split_x_y()
        self.balanced_split_x_y()
        self.pca_analysis()
        self.MNB_analysis()
        self.MNB_bal_analysis()
        self.nmf_analysis()
        self.nmf_analysis_comparison()
        self.RF_analysis()
        self.RF_bal_analysis()


        self.bal_cnn_analysis_y_cat()
        self.bal_cnn_analysis_y_cont()
        self.cnn_analysis_y_cat()
        self.cnn_analysis_y_cont()

    def load_data(self):
        '''
        Will load and process data from self.df_csv if no
        processed data is found (i.e., self.df_output_csv does not exist)
        '''
        print(f'Loading data...')
        if not os.path.isfile(self.df_output_pkl):
            self.df = pd.read_csv(self.df_csv)
            print(f'Converting strings to arrays')
            self.gen_arrays()
        else:
            print(f'Processed data found...')
            print(f'Loading data from {self.df_output_pkl}')            
            self.df = pd.read_pickle(self.df_output_pkl)
            # self.df["img_array"] = self.df["img_array"].apply(lambda x: np.array(x[1:-1].split()).astype(int))

    def gen_arrays(self):
        self.df['img_array']=self.df['pixels'].apply(self.convert_pixels_to_array)

    def convert_pixels_to_array(self, pixels):
        array = np.array([int(x) for x in pixels.split(' ')]).reshape(48,48)
        array = np.array(array, dtype='uint8')
        return array
    
    def save_df(self):
        print(f'Saving data to {self.df_output_csv}')
        self.df.to_csv(self.df_output_csv)
        print(f'Saving data to {self.df_output_pkl}')
        self.df.to_pickle(self.df_output_pkl)

    def split_x_y(self):
        t1 = self.df[self.df['Usage']!='PrivateTest']
        t2 = self.df[self.df['Usage']=='PrivateTest']
        self.x_train = np.stack(t1.pop('img_array').values)
        self.y_train = np.stack(t1.pop('emotion').values)
        self.x_test = np.stack(t2.pop('img_array').values)
        self.y_test = np.stack(t2.pop('emotion').values)
        self.x_train_flat = self.x_train.reshape(self.x_train.shape[0],-1) 
        self.x_test_flat = self.x_test.reshape(self.x_test.shape[0], -1)
        self.x_train = np.expand_dims(self.x_train, axis=3) 
        self.x_test = np.expand_dims(self.x_test, axis=3) 
        self.n_classes = len(np.unique(self.y_train))
        self.y_train_cat = to_categorical(self.y_train, self.n_classes)
        self.y_test_cat = to_categorical(self.y_test, self.n_classes)


    def balanced_split_x_y(self):
        t1 = self.df[self.df['Usage']!='PrivateTest']
        t2 = self.df[self.df['Usage']=='PrivateTest']
        self.bal_df = t1.groupby('emotion')
        self.bal_df = self.bal_df.apply(lambda x: x.sample(self.bal_df.size().min(), random_state=self.seed_val).reset_index(drop=True))
        self.bal_df_copy = self.bal_df.copy()
        self.bal_x_train = np.stack(self.bal_df.pop('img_array').values)
        self.bal_y_train = np.stack(self.bal_df.pop('emotion').values)
        self.bal_x_train_flat = self.bal_x_train.reshape(self.bal_x_train.shape[0],-1) 
        self.bal_x_train = np.expand_dims(self.bal_x_train, axis=3) 
        self.bal_y_train_cat = to_categorical(self.bal_y_train, self.n_classes)

    def plot_example_images(self):  
        # self.df.groupby('Group_Id').apply(lambda x: x.sample(1)).reset_index(drop=True)
        fig=plt.figure(figsize=(10, 3))
        columns = 7
        rows = 1
        for i in range(1, columns*rows+1):
            emo_val = i-1
            # img = np.random.randint(10, size=(h,w))
            sel_img = self.df[self.df['emotion']==emo_val]['img_array'].sample(1)
            img = np.hstack(sel_img)
            fig.add_subplot(rows, columns, i)
            plt.gca().set_title(self.emo_list[emo_val])
            plt.imshow(img)
            plt.axis('off')
        plt.savefig('../images/example_imgs.png')
        # plt.show()
        plt.close()

    def pca_analysis(self):
        fig=plt.figure(figsize=(10, 3))
        columns = 8
        rows = 1
        self.pca = decomposition.PCA(n_components=self.n_components, whiten=True)
        self.pca.fit(self.x_train_flat)
        fig.add_subplot(rows, columns, 1)
        plt.imshow(self.pca.mean_.reshape(48, 48),
                   cmap=plt.cm.bone)
        plt.gca().set_title('Overall')
        plt.axis('off')
        for i in range(2, columns*rows+1):
            emo_val = i-2
            t1 = self.df[self.df['emotion']==emo_val]
            temp_x_train = np.stack(t1.pop('img_array').values)
            temp_x_train_flat = temp_x_train.reshape(temp_x_train.shape[0],-1)
            # print(temp_x_train_flat.shape) 
            fig.add_subplot(rows, columns, i)
            pca = decomposition.PCA(n_components=self.n_components, whiten=True)
            pca.fit(temp_x_train_flat)
            plt.imshow(pca.mean_.reshape(48, 48),
                   cmap=plt.cm.bone)
            plt.gca().set_title(self.emo_list[emo_val])
            plt.axis('off')
        plt.savefig('../images/pca_images.png')
        # plt.show()
        plt.close()

    def nmf_analysis(self):
        fig=plt.figure(figsize=(10, 3))
        columns = 8
        rows = 1
        self.nmf = decomposition.NMF(n_components=self.n_components)
        self.nmf.fit(self.x_train_flat)
        fig.add_subplot(rows, columns, 1)
        plt.imshow(self.nmf.components_.mean(0).reshape(48, 48),
                   cmap=plt.cm.bone)
        plt.gca().set_title('Overall')
        plt.axis('off')
        for i in range(2, columns*rows+1):
            emo_val = i-2
            t1 = self.df[self.df['emotion']==emo_val]
            temp_x_train = np.stack(t1.pop('img_array').values)
            temp_x_train_flat = temp_x_train.reshape(temp_x_train.shape[0],-1)
            # print(temp_x_train_flat.shape) 
            fig.add_subplot(rows, columns, i)
            nmf = decomposition.NMF(n_components=self.n_components)
            nmf.fit(temp_x_train_flat)
            plt.imshow(nmf.components_.mean(0).reshape(48, 48),
                   cmap=plt.cm.bone)
            plt.gca().set_title(self.emo_list[emo_val])
            plt.axis('off')
        plt.savefig('../images/nmf_images.png')
        # plt.show()
        plt.close()

    def nmf_analysis_comparison(self, values=[1, 5, 10, 50]):
        print('Running NMF component comparisons')
        w=10
        h=10
        fig=plt.figure(figsize=(10, 2*len(values)))
        columns = 8
        rows = len(values)
        for indx, val in enumerate(values):
            self.nmf = decomposition.NMF(n_components=val)
            self.nmf.fit(self.x_train_flat)

            fig.add_subplot(rows, columns, 1+(indx*columns))
            plt.imshow(self.nmf.components_.mean(0).reshape(48, 48),
                       cmap=plt.cm.bone)
            plt.gca().set_title('Overall')
            plt.axis('off')
            for emo_val, i in enumerate(range(2, columns+1)):
                t1 = self.df[self.df['emotion']==emo_val]
                temp_x_train = np.stack(t1.pop('img_array').values)
                temp_x_train_flat = temp_x_train.reshape(temp_x_train.shape[0],-1)
                # print(temp_x_train_flat.shape) 
                fig.add_subplot(rows, columns, i+(indx*columns))
                nmf = decomposition.NMF(n_components=val)
                nmf.fit(temp_x_train_flat)
                plt.imshow(nmf.components_.mean(0).reshape(48, 48),
                       cmap=plt.cm.bone)
                plt.gca().set_title(self.emo_list[emo_val])
                plt.axis('off')
        plt.savefig('../images/nmf_images_comparison.png')
        # plt.show()
        plt.close()


    def nmf_analysis_compar_w_ave_imgs(self, values=[0, 1, 5, 10, 50]):
        print('Running NMF component comparisons')
        fig=plt.figure(figsize=(10, 2*len(values)))
        columns = 8
        rows = len(values)
        for indx, val in enumerate(values):
            self.nmf = decomposition.NMF(n_components=val)
            self.nmf.fit(self.x_train_flat)

            fig.add_subplot(rows, columns, 1+(indx*columns))
            plt.imshow(self.nmf.components_.mean(0).reshape(48, 48),
                       cmap=plt.cm.bone)
            plt.gca().set_title('Overall')
            plt.axis('off')
            for emo_val, i in enumerate(range(2, columns+1)):
                t1 = self.df[self.df['emotion']==emo_val]
                temp_x_train = np.stack(t1.pop('img_array').values)
                temp_x_train_flat = temp_x_train.reshape(temp_x_train.shape[0],-1)
                # print(temp_x_train_flat.shape) 
                fig.add_subplot(rows, columns, i+(indx*columns))
                nmf = decomposition.NMF(n_components=val)
                nmf.fit(temp_x_train_flat)
                plt.imshow(nmf.components_.mean(0).reshape(48, 48),
                       cmap=plt.cm.bone)
                plt.gca().set_title(self.emo_list[emo_val])
                plt.axis('off')
        plt.savefig('../images/nmf_images_comparison.png')
        # plt.show()
        plt.close()


    def MNB_analysis(self):
        self.MNB = MultinomialNB()
        self.MNB.fit(self.x_train_flat, self.y_train)
        self.MNB.pred_y_ = self.MNB.predict(self.x_test_flat)
        self.save_cm(self.MNB.pred_y_, 'MNB')

    def MNB_bal_analysis(self):
        print('Running balanced MNB...')
        self.MNB_bal = MultinomialNB()
        self.MNB_bal.fit(self.bal_x_train_flat, self.bal_y_train)
        self.MNB_bal.pred_y_ = self.MNB_bal.predict(self.x_test_flat)
        self.save_cm(self.MNB_bal.pred_y_, 'MNB_bal')

    def RF_analysis(self):
        print('Running Random Forest...')
        self.RF = RandomForestClassifier(n_estimators=self.n_trees,
                                        random_state=self.seed_val)
        self.RF.fit(self.x_train_flat, self.y_train)
        self.RF.pred_y_ = self.RF.predict(self.x_test_flat)
        self.save_cm(self.RF.pred_y_, 'random_forest')

    def RF_bal_analysis(self):
        print('Running balanced Random Forest...')
        self.RF = RandomForestClassifier(n_estimators=self.n_trees,
                                        random_state=self.seed_val)
        self.RF.fit(self.bal_x_train_flat, self.bal_y_train)
        self.RF.pred_y_ = self.RF.predict(self.x_test_flat)
        self.save_cm(self.RF.pred_y_, 'random_forest_bal')


    def save_cm(self, y_pred, output):
        cnf_matrix = confusion_matrix(self.y_test, y_pred.T)
        # Plot normalized confusion matrix
        plt.figure()
        plot_confusion_matrix(cnf_matrix, classes=efc.emo_list, normalize=True,
                              title=output)
        outfile = '../images/'+output+'.png'
        plt.savefig(outfile)
        # plt.show()
        plt.close()

    def cnn_analysis_y_cat(self, img_dimensions=(48,48,1)):
        self.n_classes = len(np.unique(self.y_train))
        # self.batch_size = batch_size
        # self.model = create_model(img_dimensions, self.n_classes)
        self.model = create_model4(img_dimensions, self.n_classes)
        self.train_datagen = ImageDataGenerator(preprocessing_function=preprocess_input) #, horizontal_flip=True)
        self.test_datagen = ImageDataGenerator(preprocessing_function=preprocess_input)
        self.train_datagen.fit(self.x_train)
        self.train_generator = self.train_datagen.flow(self.x_train, self.y_train_cat, 
                                                    batch_size=self.batch_size, seed=self.seed_val)
        self.test_datagen.fit(self.x_train)
        self.test_generator = self.test_datagen.flow(self.x_test, self.y_test_cat, 
                                                    batch_size=self.batch_size, seed=self.seed_val)
        self.model.compile(loss='categorical_crossentropy', optimizer='rmsprop', metrics=["accuracy"] ) # (keep)
        tensorboard = TensorBoard(log_dir='./logs_cat', batch_size=self.batch_size, write_graph=True, write_grads=True, write_images=True)
        earlystop = EarlyStopping(monitor='loss',
                                      min_delta=0,
                                      patience=2,
                                      verbose=0, mode='auto')
        self.bestmodelfilepath = "bestmodel_cat.hdf5"
        checkpoint = ModelCheckpoint(self.bestmodelfilepath, monitor='acc', verbose=1, save_best_only=True, mode='max')
        self.model.fit_generator(self.train_generator, validation_data=self.test_generator, 
                                validation_steps=100, epochs=self.n_epochs, 
                                steps_per_epoch=50, class_weight={0:   1.0,
                                     1:  999.00,
                                     2:   1.0,
                                     3:   0.01,
                                     4:   1.0,
                                     5:   1.0,
                                     6: 99.0},
                                callbacks = [tensorboard, earlystop, checkpoint])
        # self.model.fit(self.x_train, validation_data=self.y_train, validation_steps=100, epochs=25, steps_per_epoch=50, callbacks = [tensorboard, earlystop, checkpoint])
        self.best_model = load_model(self.bestmodelfilepath)
        self.metrics = self.best_model.evaluate_generator(self.test_generator, steps=5)
        self.y_pred_cat = self.best_model.predict_classes(self.x_test)
        self.save_cm(self.y_pred_cat, 'Categorical_CNN')

    def cnn_analysis_y_cont(self, img_dimensions=(48,48,1)):
        self.n_classes = len(np.unique(self.y_train))
        # self.batch_size = batch_size
        # self.model = create_model(img_dimensions, self.n_classes)
        self.model = create_model4(img_dimensions, self.n_classes)
        self.train_datagen = ImageDataGenerator(preprocessing_function=preprocess_input) #, horizontal_flip=True)
        self.test_datagen = ImageDataGenerator(preprocessing_function=preprocess_input)
        self.train_datagen.fit(self.x_train)
        self.train_generator = self.train_datagen.flow(self.x_train, self.y_train, 
                                            batch_size=self.batch_size, seed=self.seed_val)
        self.test_datagen.fit(self.x_test)
        self.test_generator = self.test_datagen.flow(self.x_test, self.y_test, 
                                            batch_size=self.batch_size, seed=self.seed_val)
        self.model.compile(loss='sparse_categorical_crossentropy', optimizer='rmsprop', metrics=["sparse_categorical_accuracy"] ) # (keep)
        tensorboard = TensorBoard(log_dir='./logs_cont', batch_size=self.batch_size, write_graph=True, write_grads=True, write_images=True)
        earlystop = EarlyStopping(monitor='loss',
                                      min_delta=0,
                                      patience=2,
                                      verbose=0, mode='auto')
        self.bestmodelfilepathcont = "bestmodel_cont.hdf5"
        checkpoint = ModelCheckpoint(self.bestmodelfilepathcont, monitor='sparse_categorical_accuracy', verbose=1, save_best_only=True, mode='max')
        self.model.fit_generator(self.train_generator, validation_data=self.test_generator, validation_steps=100, epochs=self.n_epochs, 
                                steps_per_epoch=50, class_weight={0:   1.0,
                                     1:  999.00,
                                     2:   1.0,
                                     3:   0.01,
                                     4:   1.0,
                                     5:   1.0,
                                     6: 99.0},
                                callbacks = [tensorboard, earlystop, checkpoint])
        # self.model.fit(self.x_train, validation_data=self.y_train, validation_steps=100, epochs=25, steps_per_epoch=50, callbacks = [tensorboard, earlystop, checkpoint])
        self.best_model = load_model(self.bestmodelfilepathcont)
        self.metrics = self.best_model.evaluate_generator(self.test_generator, steps=5)
        self.y_pred_cont = self.best_model.predict_classes(self.x_test)
        self.save_cm(self.y_pred_cont, 'Continuous_CNN')


    def bal_cnn_analysis_y_cat(self, img_dimensions=(48,48,1)):
        self.n_classes = len(np.unique(self.y_train))
        # self.batch_size = batch_size
        # self.model = create_model(img_dimensions, self.n_classes)
        self.model = create_model4(img_dimensions, self.n_classes)
        self.train_datagen = ImageDataGenerator(preprocessing_function=preprocess_input) #, horizontal_flip=True)
        self.test_datagen = ImageDataGenerator(preprocessing_function=preprocess_input)
        self.train_datagen.fit(self.bal_x_train)
        self.train_generator = self.train_datagen.flow(self.bal_x_train, self.bal_y_train_cat, 
                                        batch_size=self.batch_size, seed=self.seed_val)
        self.test_datagen.fit(self.bal_x_train)
        self.test_generator = self.test_datagen.flow(self.x_test, self.y_test_cat, 
                                        batch_size=self.batch_size, seed=self.seed_val)
        self.model.compile(loss='categorical_crossentropy', optimizer='rmsprop', metrics=["accuracy"] ) # (keep)
        tensorboard = TensorBoard(log_dir='./logs_cat', batch_size=self.batch_size, write_graph=True, write_grads=True, write_images=True)
        earlystop = EarlyStopping(monitor='loss',
                                      min_delta=0,
                                      patience=2,
                                      verbose=0, mode='auto')
        self.bestmodelfilepath = "bal_bestmodel_cat.hdf5"
        checkpoint = ModelCheckpoint(self.bestmodelfilepath, monitor='acc', verbose=1, save_best_only=True, mode='max')
        self.model.fit_generator(self.train_generator, validation_data=self.test_generator, 
                                validation_steps=100, epochs=self.n_epochs, 
                                steps_per_epoch=50,
                                callbacks = [tensorboard, earlystop, checkpoint])
        # self.model.fit(self.x_train, validation_data=self.y_train, validation_steps=100, epochs=25, steps_per_epoch=50, callbacks = [tensorboard, earlystop, checkpoint])
        self.best_model = load_model(self.bestmodelfilepath)
        self.metrics = self.best_model.evaluate_generator(self.test_generator, steps=5)
        self.y_pred_cat = self.best_model.predict_classes(self.x_test)
        self.save_cm(self.y_pred_cat, 'Categorical_CNN_bal')

    def bal_cnn_analysis_y_cont(self, img_dimensions=(48,48,1)):
        self.n_classes = len(np.unique(self.y_train))
        # self.batch_size = batch_size
        # self.model = create_model(img_dimensions, self.n_classes)
        self.model = create_model4(img_dimensions, self.n_classes)
        self.train_datagen = ImageDataGenerator(preprocessing_function=preprocess_input) #, horizontal_flip=True)
        self.test_datagen = ImageDataGenerator(preprocessing_function=preprocess_input)
        self.train_datagen.fit(self.bal_x_train)
        self.train_generator = self.train_datagen.flow(self.bal_x_train, self.bal_y_train, 
                                            batch_size=self.batch_size, seed=self.seed_val)
        self.test_datagen.fit(self.x_test)
        self.test_generator = self.test_datagen.flow(self.x_test, self.y_test, 
                                            batch_size=self.batch_size, seed=self.seed_val)
        self.model.compile(loss='sparse_categorical_crossentropy', optimizer='rmsprop', metrics=["sparse_categorical_accuracy"] ) # (keep)
        tensorboard = TensorBoard(log_dir='./logs_cont', batch_size=self.batch_size, write_graph=True, write_grads=True, write_images=True)
        earlystop = EarlyStopping(monitor='loss',
                                      min_delta=0,
                                      patience=2,
                                      verbose=0, mode='auto')
        self.bestmodelfilepathcont = "bal_bestmodel_cont.hdf5"
        checkpoint = ModelCheckpoint(self.bestmodelfilepathcont, monitor='acc', verbose=1, save_best_only=True, mode='max')
        self.model.fit_generator(self.train_generator, validation_data=self.test_generator, validation_steps=100, epochs=self.n_epochs, 
                                steps_per_epoch=50,
                                callbacks = [tensorboard, earlystop, checkpoint])
        # self.model.fit(self.bal_x_train, validation_data=self.bal_y_train, validation_steps=100, epochs=25, steps_per_epoch=50, callbacks = [tensorboard, earlystop, checkpoint])
        self.best_model = load_model(self.bestmodelfilepathcont)
        self.metrics = self.best_model.evaluate_generator(self.test_generator, steps=5)
        self.y_pred_cont = self.best_model.predict_classes(self.x_test)
        self.save_cm(self.y_pred_cont, 'Continuous_CNN_bal')

if __name__=='__main__':
    home = '/home/danny/Desktop/galvanize/emotion_face_classification/src/'
    cv2_path = '/home/danny/anaconda3/lib/python3.6/site-packages/cv2/data/'
    df_path = home + '../stims/fer2013/fer2013'
    if not os.path.isdir('../images'):
        os.makedirs('../images')
    efc = EmotionFaceClassifier(home, cv2_path, df_path)
    efc.run_analysis()
