import time, cv2, json
import numpy as np
from com_socket import CBackEndSocket
from matplotlib import colors, pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import animation
import multiprocessing, ctypes
import threading

class PlotSticks:

    def __init__( self, sticks_define_lines, sticks_pos_start=None, init_view=None ):
        
        self.sticks_define = self.genSticksPairs( sticks_define_lines )
        self.sticks_num = self.getSticksNum( sticks_define_lines )

        if sticks_pos_start is None:
            self.sticks_pos_buff = [np.zeros((self.sticks_num,3))]
        else:
            self.sticks_pos_buff = [sticks_pos_start]
            
        plt.ion()
        fig = plt.figure()
        self.ax = Axes3D(fig)
        if init_view is not None:
            self.ax.view_init( init_view[0], init_view[1] )
        self.anim = animation.FuncAnimation(fig, self.plotSticks, init_func=self.plotInit, frames=self.getSticksPos, repeat=False, interval=5, blit=False)
        self.axis_lim=[0,0]

    def genSticksPairs( self, sticks_lines ):
        sticks_pairs=[]
        for sticks_one_line in sticks_lines:
            if( len(sticks_one_line) < 2 ):
                continue;
            for stick_index in range(len(sticks_one_line)-1):
                temp = (sticks_one_line[stick_index], sticks_one_line[stick_index+1])
                have_it = False
                for sticks_pairs_cell in sticks_pairs:
                    if temp[0] in sticks_pairs_cell and temp[1] in sticks_pairs_cell:
                        have_it=True
                if not have_it :
                    sticks_pairs.append( temp )
        return sticks_pairs

    def getSticksNum(self, sticks_lines ):
        sticks_num_list = []
        for sticks_one_line in sticks_lines:
            for stick  in sticks_one_line:
                if stick not in sticks_num_list:
                    sticks_num_list.append( stick )
        return len(sticks_num_list)

    def setAxisLim(self, xlim,ylim,zlim ):
        self.ax.set_xlim( xlim )
        self.ax.set_ylim( ylim )
        self.ax.set_zlim( zlim )

    def setAxisTicks(self, xticks,yticks,zticks ):
        self.ax.set_xticks( xticks )
        self.ax.set_yticks( yticks )
        self.ax.set_zticks( zticks )

    def setAxisLabel( self, xlabel,ylabel,zlabel ):
        self.ax.set_xlabel( xlabel )
        self.ax.set_ylabel( ylabel )
        self.ax.set_zlabel( zlabel )

    def update( self,  sticks_pos):
        
        if self.axis_lim[0] > sticks_pos.min():
            self.axis_lim[0] = sticks_pos.min()
            self.setAxisLim(tuple(self.axis_lim),tuple(self.axis_lim),tuple(self.axis_lim))
        if self.axis_lim[1] < sticks_pos.max():
            self.axis_lim[1] = sticks_pos.max()
            self.setAxisLim(tuple(self.axis_lim),tuple(self.axis_lim),tuple(self.axis_lim))
        
        self.sticks_pos_buff.append( sticks_pos )
        plt.pause(1e-10)

    def plotInit(self):
        self.sticks_anim = [self.ax.plot(self.sticks_pos_buff[0][i,0], self.sticks_pos_buff[0][i,1], self.sticks_pos_buff[0][i,2], c='g', zorder=1 )[0] for i in self.sticks_define]
        return self.plotSticks(self.sticks_pos_buff[0] )
    
    def getSticksPos(self):
        while len(self.sticks_pos_buff) > 0:
            temp = self.sticks_pos_buff[-1]
            if( len(self.sticks_pos_buff) > 1 ):
                temp = self.sticks_pos_buff.pop(0)
            
            yield temp 

    def plotSticks( self, sticks_pos ): #sticks_pos demention: points_num x 3
        
        #self.ax.scatter( sticks_pos[:,0], sticks_pos[:,1], sticks_pos[:,2], s=10, c='r', marker='o', zorder=2  )
        for sticks_anim_cell, i in zip( self.sticks_anim, self.sticks_define):
            sticks_anim_cell._verts3d = sticks_pos[i,0], sticks_pos[i,1], sticks_pos[i,2]
        
        return self.sticks_anim

def plot_sticks( sk_pos_share, sk_pos_lock ):
    coco_ue4_pose_sticks_define=[
    #sticks define
    [0,1],[5,3,1,2,4],[11,9,7,0,6,8,10],[7,13],[6,12],[17,15,13,12,14,16]
    ]
    PlotSticks_Ins = PlotSticks( coco_ue4_pose_sticks_define, None, (-80,100) );
    PlotSticks_Ins.setAxisLabel( "aixs_X", "axis_Y", "axis_Z" )
    while( True ):
        skeleton_pos = None
        sk_pos_lock.acquire()
        if len(sk_pos_share) > 0:
            skeleton_pos = sk_pos_share[0]
            sk_pos_share.pop(0)
        sk_pos_lock.release()
        if skeleton_pos is not None:
            PlotSticks_Ins.update( skeleton_pos )
        time.sleep(0.01)

class TimerCounter():
  def __init__(self, freq) -> None:
      self.timers={}
      self.freq = freq
      self.print_counter = 0;

  def tStart(self, name ):
      if name not in self.timers.keys():
        new_timer={}
        new_timer['counter'] = 0;
        new_timer['spend'] = 0.0;
        new_timer['spend_last'] = 0.0;
        new_timer['start'] = time.time()
        self.timers[name] = new_timer
      else:
        self.timers[name]['start'] = time.time()

  def tEnd( self, name ):
      if name not in self.timers.keys():
        print("there's not timer:{}".format(name))
      else:
        self.timers[name]['counter'] = self.timers[name]['counter'] + 1;
        self.timers[name]['spend_last'] = time.time() - self.timers[name]['start']
        self.timers[name]['spend'] = self.timers[name]['spend_last'] + self.timers[name]['spend']

  def getResult( self ):
      self.print_counter = self.print_counter + 1;
      if self.print_counter >= self.freq:
        self.print_counter = 0;
        for name, timer in self.timers.items():
          print("timer:{},  spend:{} ms, counter:{}, avarage:{} ms {}fps".format(name, timer['spend']*1000.0, timer['counter'], timer['spend']*1000.0/timer['counter'], timer['counter']/timer['spend']) )
          self.timers[name]['spend'] = 0; self.timers[name]['counter'] = 0;

      return self.timers

def gen_interface_img( mc_mode,  mc_triger, mc_playback,mc_tracker, mc_status, mc_reprojection ):
    img = np.zeros((1080,120, 3), np.uint8)
    img.fill(200)
    valid_color = (255,0,0)
    invalide_color = (220,220,220)
    show_color = (0,255,0)
    cv2.rectangle(img, (10, 100), (110, 200), (0,0,255), 2)
    cv2.rectangle(img, (10, 300), (110, 400), (0,0,255), 2)
    cv2.rectangle(img, (10, 500), (110, 600), (0,0,255), 2)
    cv2.rectangle(img, (10, 700), (110, 800), (0,0,255), 2)
    cv2.putText(img, "mod_"+mc_mode, (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, valid_color, 2)
    cv2.putText(img, mc_triger, (30, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, valid_color if mc_mode == "manual" else invalide_color, 2)
    cv2.putText(img, "ply_"+mc_playback, (30, 560), cv2.FONT_HERSHEY_SIMPLEX, 0.8, valid_color, 2)
    cv2.putText(img, "prj_"+mc_reprojection, (30, 760), cv2.FONT_HERSHEY_SIMPLEX, 0.8, valid_color, 2)
    cv2.putText(img, "t:["+str(mc_tracker["x"])+","+str(mc_tracker["y"])+"]", (0, 920), cv2.FONT_HERSHEY_SIMPLEX, 0.6, valid_color if mc_mode == "manual" else invalide_color, 2)
    cv2.putText(img, "s:"+mc_status, (0, 1050), cv2.FONT_HERSHEY_SIMPLEX, 1.0, valid_color, 2)
    return img

def add_projection_points( img, projection_points_dict ):
    h,w,c = img.shape
    galvo_num = w//1440
    for galvo_index in range(galvo_num):
        x_offset = galvo_index*1440
        for coord in projection_points_dict["pose_reprojection_"+str(galvo_index)]:
            cv2.circle(img, (int(coord["x"]*1440+x_offset),int(coord["y"]*1080)), 20, (0,255,0), 2)

    return img

def rev_wide_window( ip, port, galvos_num, enable_record, mc_id_fps_share, mc_reprojection_share, id_fps_prj_lock ):
    global mc_mode, mc_triger, mc_playback, mc_tracker, mc_reprojection, cmd_sck_send, cmd_sck_recv
    def event_cam_wide_lbutton_down(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            global galvos_num, mc_mode, mc_triger, mc_playback, mc_tracker, mc_reprojection, cmd_sck_send, cmd_sck_recv
            offset_x = galvos_num*1920
            if x > (offset_x+10) and x < (offset_x+110) and y > 100 and y < 200:
                if mc_mode == "automation":
                    mc_mode = "manual"
                else:
                    mc_mode = "automation"
                cmd_sck_send.sendCMD( "mc_mode", mc_mode )

            if x > (offset_x+10) and x < (offset_x+110) and y > 300 and y < 400:
                if mc_mode == "manual":
                    if mc_triger == "finish":
                        mc_triger = "start"
                    else:
                        mc_triger = "finish"
                    cmd_sck_send.sendCMD( "mc_triger", mc_triger )

            if x > (offset_x+10) and x < (offset_x+110) and y > 500 and y < 600:
                if mc_playback == "enable":
                    mc_playback = "disable"
                else:
                    mc_playback = "enable"
                cmd_sck_send.sendCMD( "mc_playback", mc_playback )
            
            if x > (offset_x+10) and x < (offset_x+110) and y > 700 and y < 800:
                if mc_reprojection == "enable":
                    mc_reprojection = "disable"
                else:
                    mc_reprojection = "enable"

            if mc_mode == "manual":
                if x < offset_x and y < 1080 and mc_mode == "manual":
                    mc_tracker = {"cam_index":x//1920,"x":(x-(x//1920)*1920)/1920.0,"y":y/1080.0}
                    cmd_sck_send.sendCMD( "mc_tracker", mc_tracker  )
    
    tc = TimerCounter( 300 )
    tc.tStart("rev_wide")

    wide_img_sck =       CBackEndSocket(ip, port, True, True, False, False )
    cmd_sck_send =  CBackEndSocket( ip, port+2, False, False, False, True )
    cmd_sck_recv =  CBackEndSocket( ip, port+1, False, False, True, False )

    mc_mode = "automation"
    mc_triger="finish" 
    mc_tracker={"x":0,"y":0}
    mc_status="None"
    mc_playback="disable"
    mc_reprojection = "disable"

    cv2.namedWindow("cam Wide", 0)
    cv2.setMouseCallback("cam Wide",   event_cam_wide_lbutton_down)
    wide_img = np.zeros((1080,1920*galvos_num, 3), np.uint8)

    while( True ):
        rev_wide_img  = wide_img_sck.receiveWideImage(  )
        if rev_wide_img is not None:
            wide_img = rev_wide_img
            interface_img = gen_interface_img( mc_mode,  mc_triger, mc_playback, mc_tracker, mc_status, mc_reprojection )
            wide_img_show = np.concatenate((wide_img, interface_img), axis=1 )
            cv2.imshow("cam Wide", wide_img_show)
            tc.tEnd("rev_wide")
            tc.getResult()
            tc.tStart("rev_wide")

            key_press = cv2.waitKey(1) & 0xFF
            if key_press == ord('b'):
                break;
            
            id_fps_prj_lock.acquire()
            mc_reprojection_share.set( mc_reprojection )
            id_fps_prj_lock.release()

        cmd = cmd_sck_recv.receiveCMD( "mc_status" )
        if cmd is not None:
            mc_status = cmd
            print("get mc_status:",mc_status)
            if enable_record:
                if "start" in mc_status:
                    id_fps_prj_lock.acquire()
                    mc_id_fps_share.append( [mc_status[mc_status.find("_")+1:mc_status.rfind("_")], int(mc_status[mc_status.rfind("_")+1:-2])] )
                    id_fps_prj_lock.release()
                    
                elif "finished" in mc_status:
                    id_fps_prj_lock.acquire()
                    mc_id_fps_share.append(["none", 0])
                    id_fps_prj_lock.release()
                    print("stop recording file")
        
def rev_telefocus_window( ip, port, galvos_num, enable_record, mc_id_fps_share, mc_reprojection_share, id_fps_prj_lock, sk_pos_share, sk_pos_lock ):
    tc = TimerCounter( 300 )
    tc.tStart("rev_telefocus")
    img_show = False
    save_path = "./"
    save_txt_file =  None
    save_video_file = None
    mc_id = "none"
    mc_fps = 0
    mc_reprojection = "disable"

    telefocus_img_sck =  CBackEndSocket(ip, port+3, True, False, False, False )

    if img_show:
        cv2.namedWindow("cam Telefocus",0)
    telefocus_img = np.zeros((1440*galvos_num, 1080, 3), np.uint8)

    def write_video( lck_list, img_buffer, video_part ):
        #global mc_id, mc_fps, save_path
        save_video_file = None;
        mc_id_temp = "none";
        mc_fps_temp = 0
        thread_lck = lck_list[0]
        import copy
        while True:
            mc_id_read = copy.deepcopy(mc_id)
            mc_fps_read = copy.deepcopy(mc_fps)

            if mc_id_read != mc_id_temp:
                if mc_id_read != "none":
                    save_video_file = cv2.VideoWriter(save_path+mc_id_read+"_s"+str(video_part)+".avi", cv2.VideoWriter_fourcc(*'XVID'), mc_fps_read, (1440, 1080))
                    print("start recording file part[{}] id [{}] at fps [{}]".format(video_part, save_path+mc_id_read, mc_fps_read))
                else:
                    if save_video_file is not None:
                        save_video_file.release()
                        save_video_file = None
                    print("finished recording file part[{}] id [{}] at fps [{}]".format(video_part, save_path+mc_id_temp, mc_fps_temp))

                mc_id_temp = mc_id_read; mc_fps_temp = mc_fps_read;

            if save_video_file is not None:
                img_temp = None;
                thread_lck.acquire()
                if len(img_buffer) > 0:
                    img_temp = copy.deepcopy(img_buffer[0])
                    img_buffer.pop(0)
                    if len(img_buffer) >3 :
                        print("write_video buffer over flow:", len(img_buffer))
                thread_lck.release()

                if img_temp is not None:
                    save_video_file.write( img_temp )
                else:
                    time.sleep( 0.01 )
            else:
                time.sleep( 0.01 )
    
    #create writing video thread
    write_video_thread_lst = []
    write_video_lck_lst =[]
    write_video_img_buffer_lst =[]
    for galvo_index in range( galvos_num ):
        write_video_lck_lst.append( threading.Lock() )
        write_video_img_buffer_lst.append([])
        write_video_thread_lst.append( threading.Thread(target=write_video, args=([write_video_lck_lst[-1]], write_video_img_buffer_lst[-1], galvo_index)) );
        write_video_thread_lst[-1].start()
        write_video_thread_lst[-1].setName('writeVideo_'+str(galvo_index))
        print("started new thread [{}]".format(write_video_thread_lst[-1].getName()))

    while( True ):
        pos, rev_telefocus_img = telefocus_img_sck.receivePosAndTelefocusImg( )
        if pos is not None and rev_telefocus_img is not None:
            id_fps_prj_lock.acquire()
            mc_reprojection = mc_reprojection_share.get()
            id_fps_prj_lock.release()
            if mc_reprojection == "enable":
                rev_telefocus_img = add_projection_points( rev_telefocus_img, pos )

            if img_show:
                cv2.imshow("cam Telefocus", rev_telefocus_img)
                key_press = cv2.waitKey(1) & 0xFF
                if key_press == ord('b'):
                    break;
            
            tc.tEnd("rev_telefocus")
            tc.getResult()
            tc.tStart("rev_telefocus")

            # print("pose:", pos)
            skeleton_pos = np.zeros((len(pos['pose_world']),3))
            for index in range(len( pos['pose_world'] )):
                skeleton_pos[index] = np.array([float(pos['pose_world'][index]['x']),float(pos['pose_world'][index]['y']),float(pos['pose_world'][index]['z'])])
            sk_pos_lock.acquire()
            sk_pos_share.append( skeleton_pos )
            sk_pos_lock.release()
            
            if enable_record:
                mc_id_temp = None; mc_fps_temp = None;
                id_fps_prj_lock.acquire()
                if len( mc_id_fps_share ) > 0:
                    mc_id_temp = mc_id_fps_share[0][0]
                    mc_fps_temp = mc_id_fps_share[0][1]
                    mc_id_fps_share.pop(0)
                id_fps_prj_lock.release()

                if mc_id_temp is not None and mc_fps_temp is not None:
                    mc_id = mc_id_temp; mc_fps = mc_fps_temp;
                    if mc_id_temp != "none":
                        save_txt_file = open(save_path+mc_id_temp+".txt",mode='w')
                    else:
                        if save_txt_file is not None:
                            save_txt_file.close()
                            save_txt_file = None

                if save_txt_file is not None:
                    str_skeleton_pos =json.dumps(pos)
                    save_txt_file.write( str_skeleton_pos+'\n' ); 

                if mc_id != "none":
                    for galvo_index in range(galvos_num):
                        write_video_lck_lst[galvo_index].acquire()
                        write_video_img_buffer_lst[galvo_index].append( rev_telefocus_img[:, 1440*galvo_index:1440*(galvo_index+1)] )
                        write_video_lck_lst[galvo_index].release()

if __name__ == '__main__':
    from com_socket import server_ip, communication_port
    galvos_num = 2
    enable_record = True

    mc_id_fps_share =  multiprocessing.Manager().list()
    mc_reprojection_share = multiprocessing.Manager().Value( ctypes.c_char_p, 'disable' )
    id_fps_prj_lock = multiprocessing.Manager().Lock()

    sk_pos_share = multiprocessing.Manager().list()
    sk_pos_lock = multiprocessing.Manager().Lock()

    rev_wide_window_process = multiprocessing.Process(target=rev_wide_window,args=(server_ip, communication_port, galvos_num, enable_record, mc_id_fps_share, mc_reprojection_share, id_fps_prj_lock))
    rev_wide_window_process.start()
    rev_telefocus_window_process = multiprocessing.Process(target=rev_telefocus_window,args=(server_ip, communication_port, galvos_num, enable_record, mc_id_fps_share, mc_reprojection_share, id_fps_prj_lock, sk_pos_share, sk_pos_lock))
    rev_telefocus_window_process.start()
    #plot_sticks_process = multiprocessing.Process(target=plot_sticks,args=(sk_pos_share, sk_pos_lock))
    #plot_sticks_process.start()

    rev_wide_window_process.join()
    rev_telefocus_window_process.join()
    #plot_sticks_process.join()
    print("finished back_end server simulation!")