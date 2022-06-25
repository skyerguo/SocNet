import logging
import json
import redis
import pickle
import queue
import subprocess
from collections import OrderedDict, defaultdict
import os

class Redis_cache:
    def __init__(self, db, cache_size=5, use_priority_queue=True, use_LRU_cache=False):
        """初始化

        Args:
            db (int): 数据库表单
            use_priority_queue (bool, optional): 是否使用优先队列维护权值最小的点. Defaults to True.
        """
        logging.info("initing redis cache...")

        # '''从config获得参数'''
        # config = json.load(open('code/cache/redis_cache/config.json', 'r'))
        self.cache_size = int(cache_size)

        '''获得本机的IP地址，作为redis IP'''
        # self.redis_ip = "128.105.145.13"
        ret = subprocess.Popen("ifconfig eno1 | grep inet | awk '{print $2}' | cut -f 2 -d ':'",shell=True,stdout=subprocess.PIPE)
        self.redis_ip = ret.stdout.read().decode("utf-8").strip('\n')
        ret.stdout.close()

        '''连接池'''
        pool = redis.ConnectionPool(
            host=self.redis_ip,
            port=6379,
            db=db,
            password='gtcA4010',
            max_connections=None  # 连接池最大值，默认2**31
        )
        self.redis = redis.Redis(connection_pool=pool)

        '''实验开始，清空该数据库'''
        self.redis.flushdb()

        '''设置优先队列'''
        self.use_priority_queue = use_priority_queue
        if self.use_priority_queue:
            self.priority_queue = queue.PriorityQueue()

        '''设置LRU的字典'''
        self.use_LRU_cache = use_LRU_cache
        if self.use_LRU_cache:
            self.LRUcache = OrderedDict() # 用有序字典来实现LRU

        '''设置实际数据文件存储路径'''
        self.data_path = '/dev/null'

        '''设置上一层的redis_cache'''
        self.has_higher_cache = False

    def __del__(self):
        '''程序结束后，自动关闭连接，释放资源'''
        self.redis.connection_pool.disconnect()

    def remove_cache_node(self, given_key=''):
        '''删掉权值最小的cache数据'''

        '''如果有指定的key，直接删除'''
        if given_key != '':
            remove_key = given_key
        else:
            '''否则寻找权值最小的key'''
            if self.use_priority_queue:
                a = self.priority_queue.get() ## 取出并在priority_queue中去掉该元素
                min_value = a[0]
                remove_key = a[1]
            else:
                min_value = 1e9
                remove_key = -1
                for curr_key in self.redis.keys():
                    curr_value = pickle.loads(self.redis.get(name=curr_key))
                    if curr_value < min_value:
                        min_value = curr_value
                        remove_key = curr_key
        self.redis.delete(remove_key)

    def insert(self, picture_hash, picture_value, media_size=0):
        '''如果是LRU，特殊处理'''
        if self.use_LRU_cache: 
            '''若数据已存在，表示命中一次，需要把数据移到缓存队列末端'''
            if picture_hash in self.LRUcache:
                self.LRUcache.move_to_end(picture_hash)
            '''若缓存已满，则需要淘汰最早没有使用的数据'''
            if self.redis.dbsize() >= self.cache_size:
                self.LRUcache.popitem(last=False)
                self.remove_cache_node(given_key=next(iter(self.LRUcache)))
            self.LRUcache[picture_hash] = picture_value

        else:
            '''如果当前cache的空间使用完了，且不是LRU，则按照内在的权值替换'''
            if self.redis.dbsize() >= self.cache_size:
                self.remove_cache_node()
            
        
        '''插入redis数据库'''
        self.redis.set(name=picture_hash, value=pickle.dumps(picture_value))

        '''如有有使用优先队列，每次插入时需要维护优先队列'''
        if self.use_priority_queue:
            self.priority_queue.put((picture_value, picture_hash))

        '''如果需要创建图片，则在路径中创建一个文件'''
        if media_size != 0:
            if self.data_path != '/dev/null': ## 启用HTTP了
                os.system('head -c %s /dev/zero > %s'%(str(media_size), self.data_path + str(picture_hash)))

    def find(self, picture_hash):
        value = self.redis.get(name=picture_hash)
        if value:
            value = pickle.loads(value)
        else:
            value = -1
        return value

# if __name__ == '__main__':
#     r = Redis_cache(0)
#     for i in range(10):
#         r.insert(i, i)