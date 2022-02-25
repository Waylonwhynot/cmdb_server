import json

from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.
from django.views import View

from repository import models


class getServer(View):
    def get(self, request):
        ### 连接数据获取主机名列表
        token = request.META.get('HTTP_TOKEN')
        print(token)
        client_md5_token, client_time = token.split('|')
        server_token = 'xdrfdsfsdf'

        client_time = float(client_time)
        import time
        server_time = time.time()
        if server_time - client_time > 10:
            return HttpResponse('超时了')

        tmp = "%s|%s" % (server_token, client_time)
        import hashlib
        m = hashlib.md5()
        m.update(bytes(tmp, encoding='utf-8'))
        server_md5_token = m.hexdigest()

        if server_md5_token != client_md5_token:
            return HttpResponse('token值是错误的，被修改过了')

        #### 第三关 连接redis
        #### 第一次来的时候，先去redis中判断，client_md5_token 是否在redis中
        #### 如果在redis中，则代表已经访问过了，return 回去
        #### 如果不在redis中，则第一次访问，添加到redis中，并且设置过期时间
        return HttpResponse('非常重要的数据')

        ########第一种方式
        # server_token = "xdrfdsfsdf"
        # token = request.META.get('HTTP_TOKEN')
        # print(token)
        # if token != server_token:
        #     return HttpResponse('token值是错误的！')
        # return HttpResponse('非常重要的数据')

    def post(self, request):
        data = json.loads(request.body)
        #### 通过主机名获取老的数据对应的记录
        #### 加状态码判断，这里就先不加了
        hostname = data['basic']['data']['hostname']
        old_server_info = models.Server.objects.filter(hostname=hostname).first()
        if not old_server_info:
            return HttpResponse('资产不存在')
        #### 以分析disk硬盘数据为例
        #### 如果采集出错的话， 记录错误的信息
        if data['disk']['status'] != 10000:
            models.ErrorLog.objects.create(asset_obj=old_server_info, title="%s 采集硬盘出错了" % (hostname),
                                           content=data['disk']['data'])
        '''
            {
                '0': {'slot': '0', 'pd_type': 'SAS', 'capacity': '279.396', 'model': 'SEAGATE ST300MM0006     LS08S0K2B5NV'}, 
                '1': {'slot': '1', 'pd_type': 'SAS', 'capacity': '279.396', 'model': 'SEAGATE ST300MM0006     LS08S0K2B5AH'}, 
                '2': {'slot': '2', 'pd_type': 'SATA', 'capacity': '476.939', 'model': 'S1SZNSAFA01085L     Samsung SSD 850 PRO 512GB               EXM01B6Q'}, 
            }
        '''
        new_disk_info = data['disk']['data']
        print(new_disk_info)
        '''
            [
                obj(slot:0, pd_type:SAS,......),
                obj(slot:1, pd_type:SATA,......),
                ....
            ]
        '''
        old_disk_info = models.Disk.objects.filter(server_obj=old_server_info).all()  ## queryset列表
        new_slot_list = list(new_disk_info.keys())
        old_slot_list = []
        for obj in old_disk_info:
            old_slot_list.append(obj.slot)
        '''
        new_slot_list = [0, 2]
        old_slot_list = [0, 1]
        新增：new_slot_list - old_slot_list = 2
        删除：old_slot_list - new_slot_list = 1
        更新：交集
        '''
        ### 增加slot
        add_slot_list = set(new_slot_list).difference(set(old_slot_list))
        if add_slot_list:
            record_list = []
            for slot in add_slot_list:
                # {'slot': '0', 'pd_type': 'SAS', 'capacity': '279.396', 'model': 'SEAGATE ST300MM0006     LS08S0K2B5NV'}
                disk_res = new_disk_info[slot]
                tmp = "添加插槽是:{slot}, 磁盘类型是:{pd_type}, 磁盘容量是:{capacity}, 磁盘的型号：{model}".format(**disk_res)
                disk_res['server_obj'] = old_server_info
                record_list.append(tmp)
                models.Disk.objects.create(**disk_res)
            ### 将变更新的信息添加到变更记录表中
            record_str = '\n'.join(record_list)
            models.AssetRecord.objects.create(content=record_str, asset_obj=old_server_info)
        ### 删除slot
        del_slot_list = set(old_slot_list).difference(set(new_disk_info))
        if del_slot_list:
            record_str = "删除的槽位是：%s" % (";".join(del_slot_list))
            models.Disk.objects.filter(slot__in=del_slot_list, server_obj=old_server_info).delete()
            models.AssetRecord.objects.create(asset_obj=old_server_info, content=record_str)

        #### 更新硬盘数据
        up_slot_list = set(new_slot_list).intersection(set(old_slot_list))
        if up_slot_list:
            record_list = []
            for slot in up_slot_list:
                ## 新的：'0': {'slot': '0', 'pd_type': 'SAS', 'capacity': '500G', 'model': 'SEAGATE ST300MM0006     LS08S0K2B5NV'}
                new_disk_row = new_disk_info[slot]
                ### 老的：obj(slot:0, pd_type:SAS,.....)
                old_disk_row = models.Disk.objects.filter(slot=slot, server_obj=old_server_info).first()
                for k, new_v in new_disk_row.items():
                    '''
                    k:      slot, pd_type, capacity,...
                    new_v:   0     SAS       279.396,....
                    '''
                    ### 利用反射
                    ### 1. 先从老的数据中心获取老的数据
                    old_v = getattr(old_disk_row, k)
                    ### 2. 判断老的数据和新的数据是否相同
                    if old_v != new_v:
                        tmp = "槽位%s, %s由原来的%s变成了%s" % (slot, k, old_v, new_v)
                        record_list.append(tmp)
                        ### 3. 将新的数据设置回到老的数据行对象中
                        setattr(old_disk_row, k, new_v)
                ### 4. 调用save， 保存
                old_disk_row.save()
            if record_list:
                models.AssetRecord.objects.create(asset_obj=old_server_info, content=';'.join(record_list))
        return HttpResponse('ok')
