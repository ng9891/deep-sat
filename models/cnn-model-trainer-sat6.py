import os
import time
import numpy as np
import scipy.io
import tensorflow as tf
from models.layers import conv_layer, max_pool_2x2, full_layer

DATA_PATH = 'dataset/sat-6-full.mat'

# HYPERS
NUM_SAMPLES = 324000
NUM_TEST_SAMPLES = 8100
EPOCHS = 1
BATCH_SIZE = 128
STEPS = int((NUM_SAMPLES * EPOCHS) / BATCH_SIZE)
ONE_EPOCH = int(NUM_SAMPLES / BATCH_SIZE)
TEST_INTERVAL = BATCH_SIZE * 5
MODELS_TO_KEEP = 5
lr = 0.0001
decay = 0.9
momentum = 0
dropoutProb = 0.5

LABELS = os.path.join(os.getcwd(), "metadata-sat6.tsv")  # Label path for visualization
SPRITES = os.path.join(os.getcwd(), "sprite-sat6.png")

version = 'sat6-test'
output_dir = 'results-for-' + str(EPOCHS) + 'e' + str(BATCH_SIZE) + 'bs-' + version
log_dir = os.path.join(output_dir, 'logs')
log_name = 'lr' + str(lr) + 'd' + str(decay) + 'm' + str(momentum) + 'do' + str(dropoutProb)
output_file = 'output.txt'
model_dir = os.path.join(output_dir, 'trained_models')
model_name = 'saved_at_step-'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

write_to_file = open(os.path.join(output_dir, output_file), 'w')
write_to_file.write('HYPER_PARAMETERS_USED')
write_to_file.write('\n---------------------')
write_to_file.write('\nNUM_SAMPLES:' + str(NUM_SAMPLES))
write_to_file.write('\nEPOCHS:' + str(EPOCHS))
write_to_file.write('\nBATCH_SIZE:' + str(BATCH_SIZE))
write_to_file.write('\nSTEPS:' + str(STEPS))
write_to_file.write('\nLEARNING_RATE:' + str(lr))
write_to_file.write('\nDECAY:' + str(decay))
write_to_file.write('\nMOMENTUM:' + str(momentum))
write_to_file.write('\nDROPOUT:' + str(dropoutProb))


class DeepSatLoader:
    def __init__(self, key):
        self._key = key
        self._i = 0
        self.images = None
        self.labels = None

    def load_data(self):
        data = scipy.io.loadmat(DATA_PATH)
        self.images = data[self._key + '_x'].transpose(3, 0, 1, 2).astype(float) / 255
        self.labels = data[self._key + '_y'].transpose(1, 0)
        # print(self.images.shape)
        # print(self.labels.shape)
        return self

    def next_batch(self, batch_size):
        x = self.images[self._i:self._i+batch_size]
        y = self.labels[self._i:self._i+batch_size]
        self._i = (self._i + batch_size) % len(self.images)
        return x, y


class DeepSatData:
    def __init__(self):
        self.train = DeepSatLoader('train').load_data()
        self.test  = DeepSatLoader('test').load_data()


def cnn_model_trainer():
    # ALEXNET
    dataset = DeepSatData()

    x = tf.placeholder(tf.float32, shape=[None, 28, 28, 4], name='x')
    y_ = tf.placeholder(tf.float32, shape=[None, 6], name='y_')
    keep_prob = tf.placeholder(tf.float32, name='keep_prob')

    conv1 = conv_layer(x, shape=[3, 3, 4, 16], pad='VALID')
    conv1_pool = max_pool_2x2(conv1, 2, 2)

    conv2 = conv_layer(conv1_pool, shape=[3, 3, 16, 48], pad='SAME')
    conv2_pool = max_pool_2x2(conv2, 3, 3)

    conv3 = conv_layer(conv2_pool, shape=[3, 3, 48, 96], pad='SAME')
    # conv3_pool = max_pool_2x2(conv3)

    conv4 = conv_layer(conv3, shape=[3, 3, 96, 64], pad='SAME')
    # conv4_pool = max_pool_2x2(conv4)

    conv5 = conv_layer(conv4, shape=[3, 3, 64, 64], pad='SAME')
    conv5_pool = max_pool_2x2(conv5, 2, 2)

    _flat = tf.reshape(conv5_pool, [-1, 3 * 3 * 64])
    _drop1 = tf.nn.dropout(_flat, keep_prob=keep_prob)

    # full_1 = tf.nn.relu(full_layer(_drop1, 200))
    full_1 = tf.nn.relu(full_layer(_drop1, 200))
    # -- until here
    # classifier:add(nn.Threshold(0, 1e-6))
    _drop2 = tf.nn.dropout(full_1, keep_prob=keep_prob)
    full_2 = tf.nn.relu(full_layer(_drop2, 200))
    # classifier:add(nn.Threshold(0, 1e-6))
    full_3 = full_layer(full_2, 6)

    # pred = tf.nn.softmax(logits=full_3, name='pred')  # for later prediction
    pred_out = tf.argmax(full_3, 1, name='pred')

    cross_entropy = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=full_3, labels=y_))

    # train_step = tf.train.RMSPropOptimizer(lr, decay, momentum).minimize(cross_entropy)
    train_step = tf.train.AdamOptimizer(lr).minimize(cross_entropy)

    correct_prediction = tf.equal(pred_out, tf.argmax(y_, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32), name='accuracy')

    tf.summary.scalar('loss', cross_entropy)
    tf.summary.scalar('accuracy', accuracy)

    # Setting up for the visualization of the data in Tensorboard
    embedding_size = 200    # size of second to last fc layer
    embedding_input = full_2    # FC2 as input
    # Variable containing the points in visualization
    embedding = tf.Variable(tf.zeros([NUM_TEST_SAMPLES, embedding_size]), name="test_embedding")  # NUM_TEST_SAMPLES/10 = 8100
    assignment = embedding.assign(embedding_input)  # Will be passed in the test session

    merged_sum = tf.summary.merge_all()

    def test(test_sess, assign):
        x_ = dataset.test.images.reshape(10, NUM_TEST_SAMPLES, 28, 28, 4)
        y = dataset.test.labels.reshape(10, NUM_TEST_SAMPLES, 6)

        test_acc = np.mean([test_sess.run(accuracy, feed_dict={x: x_[im], y_: y[im], keep_prob: 1.0})
                            for im in range(10)])

        # Pass through the last 8100 of the test set for visualization
        test_sess.run([assign], feed_dict={x: x_[9], y_: y[9], keep_prob: 1.0})
        return test_acc

    # config=config
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        # Tensorboard
        sum_writer = tf.summary.FileWriter(os.path.join(log_dir, log_name))
        sum_writer.add_graph(sess.graph)

        # Create a Saver object
        # max_to_keep: keep how many models to keep. Delete old ones.
        saver = tf.train.Saver(max_to_keep=MODELS_TO_KEEP)

        # Setting up Projector
        config = tf.contrib.tensorboard.plugins.projector.ProjectorConfig()
        embedding_config = config.embeddings.add()
        embedding_config.tensor_name = embedding.name
        embedding_config.metadata_path = LABELS     # labels

        # Specify the width and height of a single thumbnail.
        embedding_config.sprite.image_path = SPRITES
        embedding_config.sprite.single_image_dim.extend([28, 28])
        tf.contrib.tensorboard.plugins.projector.visualize_embeddings(sum_writer, config)

        for i in range(STEPS):
            batch = dataset.train.next_batch(BATCH_SIZE)
            batch_x = batch[0]
            batch_y = batch[1]

            sess.run(train_step, feed_dict={x: batch_x, y_: batch_y, keep_prob: dropoutProb})

            _, summ = sess.run([train_step, merged_sum], feed_dict={x: batch_x, y_: batch_y, keep_prob: dropoutProb})
            sum_writer.add_summary(summ, i)

            if i % ONE_EPOCH == 0:
                ep_print = "\n*****************EPOCH: %d" % ((i/ONE_EPOCH) + 1)
                write_to_file.write(ep_print)
                print(ep_print)
            if i % TEST_INTERVAL == 0:
                acc = test(sess, assignment)
                loss = sess.run(cross_entropy, feed_dict={x: batch_x, y_: batch_y, keep_prob: dropoutProb})
                ep_test_print = "\nEPOCH:%d" % ((i/ONE_EPOCH) + 1) + " Step:" + str(i) + \
                                "|| Minibatch Loss= " + "{:.4f}".format(loss) + \
                                " Accuracy: {:.4}%".format(acc * 100)
                write_to_file.write(ep_test_print)
                print(ep_test_print)
                # Create a checkpoint in every iteration
                # saver.save(sess, os.path.join(model_dir, model_name),
                #            global_step=i)
                saver.save(sess, os.path.join(model_dir, 'model.ckpt'), global_step=i)

        test(sess, assignment)
        sum_writer.close()


def create_tsv(ds):
    # Creates the labels for the last 10,000 pictures
    labels = ['building', 'barren land', 'trees', 'grassland', 'road', 'water']
    with open('metadata-sat6.tsv', 'w') as f:
        y = ds.test.labels[-NUM_TEST_SAMPLES:]
        for i in range(NUM_TEST_SAMPLES):  # 81000/10 = 8100. Last 8100 of test data
            argmax = int(np.argmax(y[i]))
            f.write("%s \n" % labels[argmax])


def create_sprite_image(images):
    # print(type(images))
    # if isinstance(images, list):
    #     print('TRUE')
    #     images = np.array(images)
    img_h = images.shape[1]  # 28
    img_w = images.shape[2]  # 28
    n_plots = int(np.ceil(np.sqrt(images.shape[0])))  # 100

    sprite_image = np.ones((img_h * n_plots, img_w * n_plots, 3))  # (2800, 2800)

    for i in range(n_plots):
        for j in range(n_plots):
            this_filter = i * n_plots + j
            if this_filter < images.shape[0]:
                this_img = images[this_filter]
                sprite_image[i * img_h:(i + 1) * img_h, j * img_w:(j + 1) * img_w] = this_img

    return sprite_image


def mat_data_load_test():
    import matplotlib.pyplot as plt

    data = DeepSatData()

    # (10000, 28, 28, 3)
    ps = data.test.images[-NUM_TEST_SAMPLES:][..., :3]

    sprite = create_sprite_image(ps)
    plt.imsave('sprite-sat6.png', sprite, cmap='Greys')

    print(ps.shape)
    # print(data.train.images.shape)
    # print(data.train.labels.shape)
    # (400000, 28, 28, 4)
    # (400000, 4)

    create_tsv(data)

    # for i in range(4):
    #     batch = data.train.next_batch(100)
    #     print(batch[0].shape)
    #     print(batch[1].shape)
    # ind = 5
    # batch = data.train.next_batch(ind)
    # print(batch[0][0,0,0,0])
    # print(type(batch[0][0,0,0,0]))

    # plt.figure()
    # im = []
    # for i in range(ind):
    #     im.append(batch[0][:,:,:,i])
    #     print(batch[1][:,i])
    # # print(im.shape)
    # for i in range(ind):
    #     plt.imshow(im[i])
    #     plt.show()

    # plt.imshow(im)
    # plt.show()
    # display_cifar(batch[0], 28)

    '''
    (28, 28, 4, 400000)
    (4, 400000)
    (28, 28, 4, 100000)
    (4, 100000)
    (4, 2)
    '''
    # dataset = scipy.io.loadmat(DATA_PATH)
    # train_x = dataset['train_x']
    # train_y = dataset['train_y']
    #
    # test_x = dataset['test_x']
    # test_y = dataset['test_y']
    #
    # labels = dataset['annotations']
    #
    # # print(type(train_x))
    # print(train_x.shape)
    # print(train_y.shape)
    # print(test_x.shape)
    # print(test_y.shape)
    #
    # print(labels.shape)

    # for i in dataset.values():
    #     print(len(i))

    # print(type(dataset['train_y']))


if __name__ == "__main__":
    start_time = time.time()
    cnn_model_trainer()
    # mat_data_load_test()
    time_stop = "\n--- %s seconds ---" % (time.time() - start_time)
    write_to_file.write(time_stop)
    print(time_stop)
    write_to_file.close()
