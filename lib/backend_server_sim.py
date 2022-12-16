from bdb import effective
import time, cv2, json
import numpy as np
from com_socket import CBackEndSocket
from matplotlib import colors, pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import animation
from argparse import ArgumentParser

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

def gen_interface_img( mc_mode,  mc_triger, mc_playback,mc_tracker, mc_status ):
    img = np.zeros((1080,120, 3), np.uint8)
    img.fill(200)
    valid_color = (255,0,0)
    invalide_color = (220,220,220)
    show_color = (0,255,0)
    cv2.rectangle(img, (10, 100), (110, 200), (0,0,255), 2)
    cv2.rectangle(img, (10, 300), (110, 400), (0,0,255), 2)
    cv2.rectangle(img, (10, 500), (110, 600), (0,0,255), 2)
    cv2.putText(img, mc_mode, (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, valid_color, 2)
    cv2.putText(img, mc_triger, (30, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, valid_color if mc_mode == "manual" else invalide_color, 2)
    cv2.putText(img, mc_playback, (30, 560), cv2.FONT_HERSHEY_SIMPLEX, 0.8, valid_color, 2)
    cv2.putText(img, "t:["+str(mc_tracker["x"])+","+str(mc_tracker["y"])+"]", (0, 720), cv2.FONT_HERSHEY_SIMPLEX, 0.6, valid_color if mc_mode == "manual" else invalide_color, 2)
    cv2.putText(img, "s:"+mc_status, (0, 850), cv2.FONT_HERSHEY_SIMPLEX, 1.0, valid_color, 2)
    return img

if __name__ == '__main__':
    args = ArgumentParser(description="opt")
    args.add_argument(
        "--opt",
        default='wide',
        help="please enter the option: wide /telefocus",
        type=str,
    )
    opt = args.parse_args()
    sim_opt = opt.opt
    tc = TimerCounter( 300 )
    tc.tStart("rev")

    def event_cam_wide_lbutton_down(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            global galvos_num, mc_mode, mc_triger, mc_playback, mc_tracker, cmd_sck
            offset_x = galvos_num*1920
            if x > (offset_x+10) and x < (offset_x+110) and y > 100 and y < 200:
                if mc_mode == "automation":
                    mc_mode = "manual"
                else:
                    mc_mode = "automation"
                cmd_sck.sendCMD( "mc_mode", mc_mode )

            if x > (offset_x+10) and x < (offset_x+110) and y > 300 and y < 400:
                if mc_mode == "manual":
                    if mc_triger == "finish":
                        mc_triger = "start"
                    else:
                        mc_triger = "finish"
                    cmd_sck.sendCMD( "mc_triger", mc_triger )

            if x > (offset_x+10) and x < (offset_x+110) and y > 500 and y < 600:
                if mc_playback == "enable":
                    mc_playback = "disable"
                else:
                    mc_playback = "enable"
                cmd_sck.sendCMD( "mc_playback", mc_playback )

            if mc_mode == "manual":
                if x < offset_x and y < 1080 and mc_mode == "manual":
                    mc_tracker = {"x":x,"y":y}
                    cmd_sck.sendCMD( "mc_tracker", mc_tracker  )

    ip = "192.168.123.68"
    port = 6000
    if sim_opt == "wide":
        wide_img_sck =  CBackEndSocket(ip, port, True, True, False )
        cmd_sck      =  CBackEndSocket(ip, port+1, False, True, True )
    else:
        telefocus_img_sck =  CBackEndSocket(ip, port+2, True, False, False )
    run_freq = 300
    save_path = "./"
    galvos_num = 2
    enable_record = False

    mc_mode = "automation"
    mc_triger="finish" 
    mc_tracker={"x":0,"y":0}
    mc_status="None"
    mc_playback="disable"

    if sim_opt == "wide":
        cv2.namedWindow("cam Wide", 0)
        cv2.setMouseCallback("cam Wide",   event_cam_wide_lbutton_down)
    else:
        cv2.namedWindow("cam Telefocus",0)
        coco_ue4_pose_sticks_define=[
        #sticks define
        [0,1],[5,3,1,2,4],[11,9,7,0,6,8,10],[7,13],[6,12],[17,15,13,12,14,16]
        ]
        #PlotSticks_Ins = PlotSticks( coco_ue4_pose_sticks_define, None, (-80,100) )
        #PlotSticks_Ins.setAxisLabel( "aixs_X", "axis_Y", "axis_Z" )

    save_txt_file = None
    save_video_file = None
    mc_fps = 30
    mc_id = ""
    wide_img = np.zeros((1080,1920*galvos_num, 3), np.uint8)
    telefocus_img = np.zeros((1440*galvos_num, 1080, 3), np.uint8)
    imshow_flag = False;
    while( True ):
        if sim_opt == "wide":
            rev_wide_img  = wide_img_sck.receiveWideImage(  )
            if rev_wide_img is not None:
                wide_img = rev_wide_img
                interface_img = gen_interface_img( mc_mode,  mc_triger, mc_playback, mc_tracker, mc_status )
                wide_img_show = np.concatenate((wide_img, interface_img), axis=1 )
                cv2.imshow("cam Wide", wide_img_show)
                imshow_flag = True;
                tc.tEnd("rev")
                tc.getResult()
                tc.tStart("rev")

            cmd = cmd_sck.receiveCMD( "mc_status" )
            if cmd is not None:
                mc_status = cmd
                print("get mc_status:",mc_status)
                if enable_record:
                    if "start" in mc_status:
                        mc_id = mc_status[mc_status.find("_")+1:mc_status.rfind("_")]
                        mc_fps = int(mc_status[mc_status.rfind("_")+1:-2])
                        save_txt_file = open(save_path+mc_id+".txt",mode='w')
                        save_video_file = cv2.VideoWriter(save_path+mc_id+".avi", cv2.VideoWriter_fourcc(*'XVID'), mc_fps, (1440*galvos_num, 1080))
                        print("start recording file id [{}] at fps [{}]".format(save_path+mc_id, mc_fps))
                    elif "finished" in mc_status:
                        if save_txt_file is not None:
                            save_txt_file.close()
                            save_txt_file = None
                        if save_video_file is not None:
                            save_video_file.release()
                            save_video_file = None
                        print("stop recording file")

        else:
            pos, rev_telefocus_img = telefocus_img_sck.receivePosAndTelefocusImg( )
            if pos is not None and rev_telefocus_img is not None:
                cv2.imshow("cam Telefocus", rev_telefocus_img)
                imshow_flag = True;
                tc.tEnd("rev")
                tc.getResult()
                tc.tStart("rev")

                # print("pose:", pos)
                skeleton_pos = np.zeros((len(pos['pose_world']),3))
                for index in range(len( pos['pose_world'] )):
                    skeleton_pos[index] = np.array([float(pos['pose_world'][index]['x']),float(pos['pose_world'][index]['y']),float(pos['pose_world'][index]['z'])])
                #PlotSticks_Ins.update( skeleton_pos )
                
                if enable_record:
                    if save_txt_file is not None:
                        str_skeleton_pos =json.dumps(pos)
                        save_txt_file.write( str_skeleton_pos ); save_txt_file.write('\n');
                    if save_video_file is not None:
                        save_video_file.write( rev_telefocus_img )

        if imshow_flag:
            key_press = cv2.waitKey(1) & 0xFF
            if key_press == ord('b'):
                break;
            imshow_flag = False;

        # time.sleep( 1.0/run_freq )

    print("finished back_end server simulation!")