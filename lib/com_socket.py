from asyncio import sleep
from struct import pack
import numpy as np
import socket, time, cv2
from threading import Lock, Thread
import json
from turbojpeg import TurboJPEG, TJPF_BGR
import ctypes, os, copy

host_ip = "192.168.123.67"
host_port = 6000

class CAlogrithmSocket:
    def __init__(self, ip, port, enable_mass_send=False, send_wide_or_telefocus_img=False, enable_cmd_receiving=False) -> None:
        self.socket_run = True
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("created socket, target ip:[{}], target port:[{}]".format(ip, port))
        self.com_ip = ip
        self.com_port = port
        self.buffer_size = 3
        self.turbojpeg = TurboJPEG()
        if enable_mass_send:
            self.encoder_buf_lck = Lock()
            self.encoder_buf = []
            self.imgEncoder_thread = Thread(target=self.__imgEncoder, args=(send_wide_or_telefocus_img, 100) );
            self.imgEncoder_thread.start()
            self.imgEncoder_thread.setName('img_encoder_'+str(self.com_port))
            print("started new thread [{}] for encoding image data".format(self.imgEncoder_thread.getName()))
            
            self.udp_buf_lck = Lock()
            self.udp_buf = []
            self.massSend_thread = Thread(target=self.__massSend );
            self.massSend_thread.start()
            self.massSend_thread.setName('sck_mass_send_'+str(self.com_port))
            print("started new thread [{}] for udp mass sending data".format(self.massSend_thread.getName()))
            

        if enable_cmd_receiving:
            self.socket_udp.bind( ('',self.com_port) )
            self.cmd_receiving_thread = Thread(target=self.__cmd_receiving );
            self.cmd_receiving_thread.start()
            self.cmd_receiving_thread.setName('sck_cmd_rev_'+str(port))
            print("started new thread [{}] for udp command receiving data".format(self.cmd_receiving_thread.getName()))
            self.cmd_vars_lck = Lock()
            self.cmd_vars_dict = {}

    def __del__( self ):
        self.socket_run = False
        self.massSend_thread.join();
        self.cmd_receiving_thread.join();

    def sendMCStatus( self, status, id ):
        status_dict = {"mc_status": status+"_"+id}
        status_dict = json.dumps( status_dict ).encode("ascii")
        pkgs = self.__package( status_dict )
        for pkg in pkgs:
            self.socket_udp.sendto(pkg, (self.com_ip, self.com_port))

    def receiveCMD( self, cmd ):
        cmd_val = None
        self.cmd_vars_lck.acquire()
        if cmd in self.cmd_vars_dict.keys():
            cmd_val = self.cmd_vars_dict[cmd]
            self.cmd_vars_dict[cmd] = None
        self.cmd_vars_lck.release( )
        return cmd_val

    def sendWideImage( self, img ):
        self.encoder_buf_lck.acquire()
        self.encoder_buf.append( img )
        if len( self.encoder_buf ) > self.buffer_size:
            print("encode wide image buffer overflow:{}".format( len(self.encoder_buf)))
        self.encoder_buf_lck.release();

    def sendPosAndTelefocusImg( self, img, pos ):
        self.encoder_buf_lck.acquire()
        self.encoder_buf.append( [pos, img] )
        if len( self.encoder_buf ) > self.buffer_size:
            print("encode pos and telefocus img buffer overflow:{}".format( len(self.encoder_buf)))
        self.encoder_buf_lck.release();

    def __imgEncoder( self, send_wide_or_telefocus_img, quality ):
        while( self.socket_run ):
            if send_wide_or_telefocus_img:
                self.__encodeWideImage( quality )
            else:
                self.__encodePosAndTelefocusImg( quality )

    def __massSend( self ):
        while( self.socket_run ):
            pkgs = None
            self.udp_buf_lck.acquire();
            if len( self.udp_buf ) > 0:
                pkgs = self.udp_buf[0]
                self.udp_buf.pop(0)
            self.udp_buf_lck.release();
            if pkgs  is not None:
                for pkg in pkgs:
                    self.socket_udp.sendto(pkg, (self.com_ip, self.com_port))
            else:
                time.sleep( 0.001 )

    def __encodeWideImage( self, quality=100 ):
        img = None
        self.encoder_buf_lck.acquire( )
        if len( self.encoder_buf ) > 0:
            img  = self.encoder_buf[0]
            self.encoder_buf.pop(0)
        self.encoder_buf_lck.release()

        if img is not None:
            #_, img_code = cv2.imencode('.jpg', img,[int(cv2.IMWRITE_JPEG_QUALITY),quality] )
            #img_code = img_code.tostring()
            img_code = self.turbojpeg.encode( img )
            pkgs = self.__package( img_code )
            self.udp_buf_lck.acquire();
            self.udp_buf.append( pkgs )
            if len( self.udp_buf ) > self.buffer_size:
                print("udp sending buffer overflow, port: {}, num:{}".format( self.com_port, len(self.udp_buf)))
            self.udp_buf_lck.release();
        else:
            time.sleep( 0.001 )

    def __encodePosAndTelefocusImg( self, quality=100):
        pos = None; img  = None
        self.encoder_buf_lck.acquire( )
        if len( self.encoder_buf ) > 0:
            pos, img  = self.encoder_buf[0]
            self.encoder_buf.pop(0)
        self.encoder_buf_lck.release()

        if pos is not None:
            #_, img_code = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY),quality] )
            #img_code = img_code.tostring()
            img_code = self.turbojpeg.encode( img )
            pos_code = json.dumps( pos ).encode("ascii")
            pos_code = self.__alignCompletion( pos_code, 3000 )
            pos_img_code = pos_code + img_code
            pkgs = self.__package( pos_img_code )
            self.udp_buf_lck.acquire();
            self.udp_buf.append( pkgs )
            if len( self.udp_buf ) > self.buffer_size:
                print("udp sending buffer overflow, port: {}, num:{}".format( self.com_port, len(self.udp_buf)))
            self.udp_buf_lck.release();
        else:
            time.sleep( 0.001 )

    def __cmd_receiving( self ):
        pkg_body = None
        while( self.socket_run ):
            pkg, addr = self.socket_udp.recvfrom( 9100 )
            if addr[0] == self.com_ip:
                pkg_body, received_finished = self.__parseRevPkgHead( pkg, pkg_body )
                if received_finished and pkg_body is not None:
                    self.cmd_vars_lck.acquire()
                    self.cmd_vars_dict.update( self.__parseRevPkgBodyControlVars( pkg_body ) )
                    self.cmd_vars_lck.release()
                    pkg_body = None

    def __parseRevPkgHead( self, pkg, pkg_body ):
        pkg_head = json.loads(pkg[:100].decode("ascii"))
        received_finished = False
        if pkg_head['all_pkgs'] == pkg_head['pkg_index'] + 1:
            received_finished = True
        
        if received_finished:
            if pkg_head['pkg_index'] == 0:
                pkg_body = pkg[100:100+pkg_head['last_pkg_len']]
            elif pkg_body is not None:
                pkg_body = pkg_body + pkg[100:100+pkg_head['last_pkg_len']]
        else:
            if pkg_head['pkg_index'] == 0:
                pkg_body = pkg[100:9100]
            elif pkg_body is not None:
                pkg_body = pkg_body + pkg[100:9100]

        return pkg_body, received_finished

    def __parseRevPkgBodyControlVars( self, pkg_body ):
        return json.loads(pkg_body.decode("ascii"))

    def __package( self, pkgs_body ):
        all_pkgs = len(pkgs_body)//9000
        last_pkg_len = len(pkgs_body) - all_pkgs*9000
        if last_pkg_len == 0:
            last_pkg_len= 9000
        else:
            all_pkgs = all_pkgs + 1

        packages = []
        for i in range( all_pkgs ):
            if all_pkgs == i+1:
                pkg_body = pkgs_body[i*9000:i*9000+last_pkg_len]
                pkg_body = self.__alignCompletion( pkg_body, 9000 )
            else:
                pkg_body = pkgs_body[i*9000:(i+1)*9000]
            pkg_head = {"all_pkgs":all_pkgs,"pkg_index":i,"last_pkg_len":last_pkg_len}
            pkg_head = json.dumps( pkg_head ).encode("ascii")
            pkg_head = self.__alignCompletion( pkg_head, 100 )
            package = pkg_head + pkg_body
            packages.append( package )

        return packages

    def __alignCompletion(self, pkg, all_size ):
        if len(pkg) >= all_size:
            return pkg 

        align_str = ""
        for i in range( all_size - len(pkg) ):
            align_str = align_str + " "
        align_str = align_str.encode("ascii")
        pkg = pkg + align_str
        return pkg

class CBackEndSocket: #using c++ library
    def __init__(self, ip, port, enable_mass_receiving=False, receive_wide_or_telefocus_img = False, enable_cmd_receiving=False) -> None:
        self.socket_run = True
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.com_ip = ip
        self.com_port = port
        self.buffer_size = 3
        self.turbojpeg = TurboJPEG()
        if enable_mass_receiving:
            self.lib = ctypes.cdll.LoadLibrary(os.path.dirname(__file__)+'/libudp_socket.so')
            self.lib.massReceiving.argtypes = ( ctypes.c_int, ctypes.c_int )
            self.lib.readPkgBdy.argtypes = ( ctypes.POINTER(ctypes.c_int), )
            self.lib.readPkgBdy.restype = ctypes.POINTER(ctypes.c_ubyte)
            self.massReceive_thread = Thread(target=self.__massReceive, args=(self.com_port, 9100) );
            self.massReceive_thread.start()
            self.massReceive_thread.setName('sck_mass_rev_'+str(self.com_port))
            print("started new thread [{}] for udp mass receiving data".format(self.massReceive_thread.getName()))

            self.decoder_buf_lck = Lock()
            self.decoder_buf = []
            self.imgDecoder_thread = Thread(target=self.__imgDecoder, args=(receive_wide_or_telefocus_img,) );
            self.imgDecoder_thread.start()
            self.imgDecoder_thread.setName('img_decoder_'+str(self.com_port))
            print("started new thread [{}] for decoding image data".format(self.imgDecoder_thread.getName()))
            
        if enable_cmd_receiving:
            self.socket_udp.bind( ('',self.com_port) )
            self.cmd_receiving_thread = Thread(target=self.__cmd_receiving );
            self.cmd_receiving_thread.start()
            self.cmd_receiving_thread.setName('sck_cmd_rev_'+str(self.com_port))
            print("started new thread [{}] for udp command receiving data".format(self.cmd_receiving_thread.getName()))
            self.cmd_vars_lck = Lock()
            self.cmd_vars_dict = {}

    def __del__( self ):
        self.socket_run = False
        self.lib.stopReceiving()
        self.massReceive_thread.join();
        self.cmd_receiving_thread.join();

    def sendCMD( self, cmd, cmd_val ):
        cmd_dict = {cmd: cmd_val}
        cmd_dict = json.dumps( cmd_dict ).encode("ascii")
        pkgs = self.__package( cmd_dict )
        for pkg in pkgs:
            self.socket_udp.sendto(pkg, (self.com_ip, self.com_port))

    def receiveCMD( self, cmd ):
        cmd_val = None
        self.cmd_vars_lck.acquire()
        if cmd in self.cmd_vars_dict.keys():
            cmd_val = self.cmd_vars_dict[cmd]
            self.cmd_vars_dict[cmd] = None
        self.cmd_vars_lck.release( )
        return cmd_val

    def receiveWideImage( self ):
        img = None
        self.decoder_buf_lck.acquire(  )
        if len( self.decoder_buf ) > 0:
            img = self.decoder_buf[0]
            self.decoder_buf.pop( 0 )
        self.decoder_buf_lck.release()
        return img

    def receivePosAndTelefocusImg( self ):
        pos = None; img = None
        self.decoder_buf_lck.acquire(  )
        if len( self.decoder_buf ) > 0:
            pos, img = self.decoder_buf[0]
            self.decoder_buf.pop( 0 )
        self.decoder_buf_lck.release()
        return pos, img

    def __massReceive( self, port, pkg_size ):
        self.lib.massReceiving( int(port), int(pkg_size) )

    def __imgDecoder(self, receive_wide_or_telefocus_img):
        while( self.socket_run ):
            if receive_wide_or_telefocus_img:
                self.__decodeWideImage(  )
            else:
                self.__decodePosAndTelefocusImg(  )
            
    def __decodeWideImage( self ):
        img_code = None
        #read from buffer
        c_pkg_bdy_size = ctypes.c_int(0)
        img_code_ptr = self.lib.readPkgBdy(  ctypes.pointer( c_pkg_bdy_size ) );
        pkg_bdy_size = c_pkg_bdy_size.value
        if pkg_bdy_size > 0:                        
            img_code = copy.deepcopy( ctypes.string_at( img_code_ptr, pkg_bdy_size ) )
            self.lib.delPkgBdy();

        if img_code is not None:
            #img_code = np.frombuffer( img_code, dtype = "uint8" )
            #img = cv2.imdecode( img_code, cv2.IMREAD_COLOR )
            img = self.turbojpeg.decode( img_code, pixel_format=TJPF_BGR )
            self.decoder_buf_lck.acquire()
            self.decoder_buf.append( img )
            if len( self.decoder_buf ) > self.buffer_size:
                print("decode wide image buffer overflow:{}".format( len(self.decoder_buf)))
                self.decoder_buf.pop(0)
            self.decoder_buf_lck.release( )
        else:
            sleep( 0.0001 )

    def __decodePosAndTelefocusImg( self ):
        pos_img_code = None
        #read from buffer
        c_pkg_bdy_size = ctypes.c_int(0)
        pos_img_code_ptr = self.lib.readPkgBdy(  ctypes.pointer( c_pkg_bdy_size ) );
        pkg_bdy_size = c_pkg_bdy_size.value
        if pkg_bdy_size > 0:
            pos_img_code = copy.deepcopy( ctypes.string_at( pos_img_code_ptr, pkg_bdy_size ) )
            self.lib.delPkgBdy();

        if pos_img_code is not None:
            #img_code = np.frombuffer( img_code, dtype = "uint8" )
            #img = cv2.imdecode( img_code, cv2.IMREAD_COLOR )
            img = self.turbojpeg.decode( pos_img_code[3000:], pixel_format=TJPF_BGR)
            pos_code = pos_img_code[:3000].decode("ascii")
            pos = json.loads(pos_code)
            self.decoder_buf_lck.acquire()
            self.decoder_buf.append( [pos, img] )
            if len( self.decoder_buf ) > self.buffer_size:
                print("decode pos_telefocus image buffer overflow:{}".format( len(self.decoder_buf)))
                self.decoder_buf.pop(0)
            self.decoder_buf_lck.release( )
        else:
            sleep( 0.0001 )

    def __cmd_receiving( self ):
        pkg_body = None
        while( self.socket_run ):
            pkg, addr = self.socket_udp.recvfrom( 9100 )
            if addr[0] == self.com_ip:
                pkg_body, received_finished = self.__parseRevPkgHead( pkg, pkg_body )
                if received_finished and pkg_body is not None:
                    self.cmd_vars_lck.acquire()
                    self.cmd_vars_dict.update( self.__parseRevPkgBodyControlVars( pkg_body ) )
                    self.cmd_vars_lck.release()
                    pkg_body = None

    def __parseRevPkgHead( self, pkg, pkg_body ):
        pkg_head = json.loads(pkg[:100].decode("ascii"))
        received_finished = False
        if pkg_head['all_pkgs'] == pkg_head['pkg_index'] + 1:
            received_finished = True
        
        if received_finished:
            if pkg_head['pkg_index'] == 0:
                pkg_body = pkg[100:100+pkg_head['last_pkg_len']]
            elif pkg_body is not None:
                pkg_body = pkg_body + pkg[100:100+pkg_head['last_pkg_len']]
        else:
            if pkg_head['pkg_index'] == 0:
                pkg_body = pkg[100:9100]
            elif pkg_body is not None:
                pkg_body = pkg_body + pkg[100:9100]

        return pkg_body, received_finished
    
    def __parseRevPkgBodyControlVars( self, pkg_body ):
        return json.loads(pkg_body.decode("ascii"))

    def __package( self, pkgs_body ):
        all_pkgs = len(pkgs_body)//9000
        last_pkg_len = len(pkgs_body) - all_pkgs*9000
        if last_pkg_len == 0:
            last_pkg_len= 9000
        else:
            all_pkgs = all_pkgs + 1

        packages = []
        for i in range( all_pkgs ):
            if all_pkgs == i+1:
                pkg_body = pkgs_body[i*9000:i*9000+last_pkg_len]
                pkg_body = self.__alignCompletion( pkg_body, 9000 )
            else:
                pkg_body = pkgs_body[i*9000:(i+1)*9000]
            pkg_head = {"all_pkgs":all_pkgs,"pkg_index":i,"last_pkg_len":last_pkg_len}
            pkg_head = json.dumps( pkg_head ).encode("ascii")
            pkg_head = self.__alignCompletion( pkg_head, 100 )
            package = pkg_head + pkg_body
            packages.append( package )

        return packages

    def __alignCompletion(self, pkg, all_size ):
        if len(pkg) >= all_size:
            return pkg 

        align_str = ""
        for i in range( all_size - len(pkg) ):
            align_str = align_str + " "
        align_str = align_str.encode("ascii")
        pkg = pkg + align_str
        return pkg


if __name__ == '__main__':
    from backend_server_sim import TimerCounter
    tc = TimerCounter(300)
    tc.tStart("send")

    wide_img_sck =  CAlogrithmSocket(host_ip, host_port, True, True, False )
    cmd_sck      =  CAlogrithmSocket(host_ip, host_port+1, False, True , True )
    telefocus_img_sck =  CAlogrithmSocket(host_ip, host_port+2, True, False, False )
    run_freq = 50
    galvos_num = 2

    mc_mode = "automation"
    mc_triger="finish" 
    mc_tracker=[0,0]
    mc_status="finished"
    mc_playback="disable"
    mc_id = ""

    cv2.namedWindow("cam_Wide_Send",0)
    cv2.namedWindow("cam_Telefocus_Send",0)

    wide_img = np.zeros((1080,1920*galvos_num, 3), np.uint8)
    telefocus_img = np.zeros((1080, 1440*galvos_num, 3), np.uint8)
    pos_num = 0
    while( True ):
        cmd = cmd_sck.receiveCMD( "mc_mode" )
        if cmd is not None:
            mc_mode = cmd
            print("get mc_mode: ",mc_mode)

        cmd = cmd_sck.receiveCMD( "mc_triger" )
        if cmd is not None:
            mc_triger = cmd
            print("get mc_triger: ",mc_triger)
            if mc_triger == "start":
                mc_status = "start"
                mc_id = time.strftime("%Y_%m_%d_%H_%M_%S")
                if mc_playback == "enable":
                    mc_id = "p_"+mc_id
                
        cmd = cmd_sck.receiveCMD( "mc_tracker" )
        if cmd is not None:
            mc_tracker = cmd
            print("get mc_tracker: ",mc_tracker)

        send_wide_img  = cv2.putText(wide_img.copy(), str(time.time()), (600, 1000), cv2.FONT_HERSHEY_SIMPLEX, 6.0, (255,255,255), 2)
        send_telefocus_img  = cv2.putText(telefocus_img.copy(), str(time.time()), (300, 500), cv2.FONT_HERSHEY_SIMPLEX, 6.0, (255,255,255), 2)
        pos_num = pos_num + 1
        if pos_num > 1000:
            pos_num = 0
        pos = {"pose_world":[{"x":i+pos_num,"y":i+pos_num+1, "z":i+pos_num+2 } for i in range(18)] }
        #sending pictures
        wide_img_sck.sendWideImage( send_wide_img )
        telefocus_img_sck.sendPosAndTelefocusImg( send_telefocus_img, pos )
        
        cv2.imshow("cam_Wide_Send", send_wide_img)
        cv2.imshow("cam_Telefocus_Send", send_telefocus_img)

        key_press = cv2.waitKey(1) & 0xFF
        if key_press == ord('b'):
            break;

        tc.tEnd("send")
        tc.getResult()
        tc.tStart("send")
        time.sleep( 1.0/run_freq )

    print("finished back_end server simulation!")