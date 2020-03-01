import os
# os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import tkinter as tk
import numpy as np
import pyttsx3
import cv2
from PIL import Image
import scipy
from keras.models import load_model
from keras import backend as K
import time
import seaborn as sns
from keras.layers import Layer
import argparse

converter = pyttsx3.init()
converter.setProperty('rate', 220) 
converter.setProperty('volume', 1.0)

class MaxPoolingWithArgmax2D(Layer):

    def __init__(
            self,
            pool_size=(2, 2),
            strides=(2, 2),
            padding='same',
            **kwargs):
        super(MaxPoolingWithArgmax2D, self).__init__(**kwargs)
        self.padding = padding
        self.pool_size = pool_size
        self.strides = strides

    def call(self, inputs, **kwargs):
        padding = self.padding
        pool_size = self.pool_size
        strides = self.strides
        if K.backend() == 'tensorflow':
            ksize = [1, pool_size[0], pool_size[1], 1]
            padding = padding.upper()
            strides = [1, strides[0], strides[1], 1]
            output, argmax = K.tf.nn.max_pool_with_argmax(
                    inputs,
                    ksize=ksize,
                    strides=strides,
                    padding=padding)
        else:
            errmsg = '{} backend is not supported for layer {}'.format(
                    K.backend(), type(self).__name__)
            raise NotImplementedError(errmsg)
        argmax = K.cast(argmax, K.floatx())
        return [output, argmax]

    def compute_output_shape(self, input_shape):
        ratio = (1, 2, 2, 1)
        output_shape = [
                dim//ratio[idx]
                if dim is not None else None
                for idx, dim in enumerate(input_shape)]
        output_shape = tuple(output_shape)
        return [output_shape, output_shape]

    def compute_mask(self, inputs, mask=None):
        return 2 * [None]


class MaxUnpooling2D(Layer):
    def __init__(self, size=(2, 2), **kwargs):
        super(MaxUnpooling2D, self).__init__(**kwargs)
        self.size = size

    def call(self, inputs, output_shape=None):
        updates, mask = inputs[0], inputs[1]
        with K.tf.variable_scope(self.name):
            mask = K.cast(mask, 'int32')
            input_shape = K.tf.shape(updates, out_type='int32')
            #  calculation new shape
            if output_shape is None:
                output_shape = (
                        input_shape[0],
                        input_shape[1]*self.size[0],
                        input_shape[2]*self.size[1],
                        input_shape[3])
            self.output_shape1 = output_shape

            # calculation indices for batch, height, width and feature maps
            one_like_mask = K.ones_like(mask, dtype='int32')
            batch_shape = K.concatenate(
                    [[input_shape[0]], [1], [1], [1]],
                    axis=0)
            batch_range = K.reshape(
                    K.tf.range(output_shape[0], dtype='int32'),
                    shape=batch_shape)
            b = one_like_mask * batch_range
            y = mask // (output_shape[2] * output_shape[3])
            x = (mask // output_shape[3]) % output_shape[2]
            feature_range = K.tf.range(output_shape[3], dtype='int32')
            f = one_like_mask * feature_range

            # transpose indices & reshape update values to one dimension
            updates_size = K.tf.size(updates)
            indices = K.transpose(K.reshape(
                K.stack([b, y, x, f]),
                [4, updates_size]))
            values = K.reshape(updates, [updates_size])
            ret = K.tf.scatter_nd(indices, values, output_shape)
            return ret
          
    def compute_output_shape(self, input_shape):
            mask_shape = input_shape[1]
            return (
                mask_shape[0],
                mask_shape[1]*self.size[0],
                mask_shape[2]*self.size[1],
                mask_shape[3]
)

def give_color_to_seg_img(seg, n_classes):
    '''
    seg : (input_width,input_height,3)
    '''

    if len(seg.shape) == 3:
        seg = seg[:, :, 0]
    seg_img = np.zeros((seg.shape[0], seg.shape[1], 3)).astype('float')
    colors = sns.color_palette("hls", n_classes)

    for c in range(n_classes):
        if (c == 1 ):
            segc = (seg == c)
            seg_img[:, :, 0] += (segc * (colors[c][0]))
            seg_img[:, :, 1] += (segc * (colors[c][1]))
            seg_img[:, :, 2] += (segc * (colors[c][2]))

    return (seg_img)

net = cv2.dnn.readNetFromCaffe("/home/inthiyaz-b-k/Desktop/End_to_End_ADAS_System/MobileNetSSD_deploy.prototxt", "/home/inthiyaz-b-k/Desktop/End_to_End_ADAS_System/MobileNetSSD_deploy.caffemodel")
classNames = { 0: 'background',
    1: 'aeroplane', 2: 'bicycle', 3: 'bird', 4: 'boat',
    5: 'bottle', 6: 'bus', 7: 'car', 8: 'cat', 9: 'chair',
    10: 'cow', 11: 'diningtable', 12: 'dog', 13: 'horse',
    14: 'motorbike', 15: 'person', 16: 'pottedplant',
    17: 'sheep', 18: 'sofa', 19: 'train', 20: 'tvmonitor' }
count = 0

model = load_model('/home/inthiyaz-b-k/Desktop/Lane_Segmentation/final-smaller(large_checkpoint).h5', custom_objects={'MaxPoolingWithArgmax2D': MaxPoolingWithArgmax2D, 'MaxUnpooling2D': MaxUnpooling2D})
unet = load_model('/home/inthiyaz-b-k/Desktop/HackVerse/DAS/DAS_1.hdf5')
# model.summary()
# unet.summary()
max_seq_len = 1
x_train=[]
frames=[]
predict=[]

def activate():
    # cap = cv2.VideoCapture(0)
    vid = cv2.VideoCapture("/home/inthiyaz-b-k/Downloads/splice.mp4")

    while(vid.isOpened()):
        _, img = vid.read()
        image_ = cv2.resize(img, (512,512))
        cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)
        cv2.moveWindow("Frame", 0,0)
        cv2.imshow("Frame", image_)

        frame = np.copy(image_)
        expand_frame = np.expand_dims(image_, axis = 0) # expand the dimension to meet the dimensionality requirement of the model
        y_pred = model.predict(expand_frame) # predict the output

        y_predi = np.argmax(y_pred, axis=3)
        x=give_color_to_seg_img(y_predi[0], 3)
        cv2.imwrite('buffer.png', x*255)
        x = cv2.imread('buffer.png')
        img_rgb = cv2.cvtColor(x, cv2.COLOR_BGR2RGB)
        threshold = [[94, 219 , 86], [97, 221, 88]]
        mask = cv2.inRange(img_rgb, np.array(threshold[0]), np.array(threshold[1]))
        cv2.namedWindow("Lane_Segmentation", cv2.WINDOW_NORMAL)
        cv2.moveWindow("Lane_Segmentation", 1200,600)
        cv2.imshow("Lane_Segmentation", mask)

        if len(mask.shape) != 2:
            gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        else:
            gray = mask

        gray = cv2.bitwise_not(gray)
        bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, \
                                    cv2.THRESH_BINARY, 3, -2)


        horizontal = np.copy(bw)

        cols = horizontal.shape[1]
        horizontal_size = cols // 30

        # Create structure element for extracting horizontal lines through morphology operations
        horizontalStructure = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))

        # Apply morphology operations
        horizontal = cv2.erode(horizontal, horizontalStructure)
        horizontal = cv2.dilate(horizontal, horizontalStructure)

        # Show extracted horizontal lines
        # show_wait_destroy("horizontal", horizontal)
        # cv2.imshow("horizontal", horizontal)

        ret, thresh = cv2.threshold(horizontal, 127, 255, 0)
        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        # print(len(contours))
        if(len(contours) != 0):
            count += 1
            if(count >= 5):
                # print("Alert! cross section is there")
                converter.say("Alert cross section is there")
        else:
            count = 0
        
        frame_ = cv2.resize(img, (224, 224)) / 127.5 -1 # pre-processing the frames as done in training process
        expand_frame_ = np.expand_dims(frame_, axis = 0) # expand the dimension to meet the dimensionality requirement of the model
        pred = unet.predict(expand_frame_) # predict the output
        pred = pred[0]
        cv2.namedWindow("DAS", cv2.WINDOW_NORMAL)
        cv2.moveWindow("DAS", 1200,0)
        cv2.imshow("DAS", pred)
        frame_resized = cv2.resize(img,(300,300))

        blob = cv2.dnn.blobFromImage(frame_resized, 0.007843, (300, 300), (127.5, 127.5, 127.5), False)
        #Set to network the input blob 
        net.setInput(blob)
        #Prediction of network
        detections = net.forward()

        #Size of frame resize (300x300)
        cols = frame_resized.shape[1] 
        rows = frame_resized.shape[0]

        #For get the class and location of object detected, 
        # There is a fix index for class, location and confidence
        # value in @detections array .
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2] #Confidence of prediction 
            if confidence > 0.3: # Filter prediction 
                class_id = int(detections[0, 0, i, 1]) # Class label

                # Object location 
                xLeftBottom = int(detections[0, 0, i, 3] * cols) 
                yLeftBottom = int(detections[0, 0, i, 4] * rows)
                xRightTop   = int(detections[0, 0, i, 5] * cols)
                yRightTop   = int(detections[0, 0, i, 6] * rows)
                
                # Factor for scale to original size of frame
                heightFactor = frame.shape[0]/300.0  
                widthFactor = frame.shape[1]/300.0 
                # Scale object detection to frame
                xLeftBottom = int(widthFactor * xLeftBottom) 
                yLeftBottom = int(heightFactor * yLeftBottom)
                xRightTop   = int(widthFactor * xRightTop)
                yRightTop   = int(heightFactor * yRightTop)
                # Draw location of object  
                cv2.rectangle(frame, (xLeftBottom, yLeftBottom), (xRightTop, yRightTop),
                                (0, 255, 0))

                # Draw label and confidence of prediction in frame resized
                if class_id in classNames:
                    label = classNames[class_id] + ": " + str(confidence)
                    labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

                    yLeftBottom = max(yLeftBottom, labelSize[1])
                    cv2.rectangle(frame, (xLeftBottom, yLeftBottom - labelSize[1]),
                                            (xLeftBottom + labelSize[0], yLeftBottom + baseLine),
                                            (255, 255, 255), cv2.FILLED)
                    cv2.putText(frame, label, (xLeftBottom, yLeftBottom),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0))
                    xmin = xLeftBottom
                    xmax = xRightTop

                    if (frame.shape[0]//40) <= xmin <= (frame.shape[0]//60) or (frame.shape[0]//60) <= xmin <= (frame.shape[0]):
                        # print('Alert, Object is in ROI !!!')
                        converter.say("Alert obstacle is there ")
                        

                    # print(label) #print class and confidence
        converter.runAndWait()
        # cv2.namedWindow("frame", cv2.WINDOW_NORMAL)
        # cv2.imshow("frame", frame)
        cv2.namedWindow("Object_Detection", cv2.WINDOW_NORMAL)
        cv2.moveWindow("Object_Detection", 0,600)
        cv2.imshow("Object_Detection", frame)

        if(cv2.waitKey(1) == 27):
            break
    cv2.destroyAllWindows()
    vid.release()
    




rootwindow=tk.Tk()

# rootwindow.overrideredirect(True)
rootwindow.geometry("{0}x{1}+0+0".format(rootwindow.winfo_screenwidth(), rootwindow.winfo_screenheight()))
#rootwindow.focus_set()  # <-- move focus to this widget
# rootwindow.bind("<Escape>", lambda e: rootwindow.destroy())

rootwindow.title('Diksoochi')

#Title
tk.Label(text="Diksoochi",font="Arial 30 bold").place(relx=0.5, rely=0.1, anchor=tk.CENTER)    
# tk.Label(text="* ",font="Arial 16").pack()


#Buttons
activateButton=tk.Button(rootwindow,text="Activate Diksoochi",width="25",font="Arial 25",command=activate)
activateButton.place(relx=0.5,rely=0.5,anchor=tk.CENTER)

activateButton=tk.Button(rootwindow,text="Press 'ESC' to Deactivate",width="30",font="Arial 25")
activateButton.place(relx=0.5,rely=0.6,anchor=tk.CENTER)



rootwindow.mainloop()