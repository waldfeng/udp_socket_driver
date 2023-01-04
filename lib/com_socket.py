from asyncio import sleep
from struct import pack
import numpy as np
import socket, time, cv2
from threading import Lock, Thread
import json
from turbojpeg import TurboJPEG, TJPF_BGR
#from nvjpeg import NvJpeg
import ctypes, os, copy

server_ip = "192.168.123.68"
host_ip = "192.168.123.67"
communication_port = 6000

class CAlogrithmSocket:
    def __init__(self, ip, port, enable_mass_send=False, send_wide_or_telefocus_img=False, enable_cmd_receiving=False, enable_cmd_sending=False, encode_quality = 40 ) -> None:
        self.socket_run = True
        self.socket_tcp = None
        self.new_connection = None
        self.com_ip = ip
        self.com_port = port
        self.encode_quality = encode_quality
        self.buffer_size = 3
        self.pkg_head_len = 20
        self.turbojpeg = TurboJPEG()
        # self.nj = NvJpeg()

        if enable_mass_send + enable_cmd_sending + enable_cmd_receiving > 1:
            print("error: init CAlogrithmSocket")

        if enable_cmd_sending:
            self.cmd_send_lck = Lock()
            self.cmd_send_dict = {}
            self.cmd_send_thread = Thread(target=self.__cmdSend );
            self.cmd_send_thread.start()
            self.cmd_send_thread.setName('sck_cmd_send'+str(self.com_port))
            print("started new thread [{}] for tcp communication of command data".format(self.cmd_send_thread.getName()))    
        
        if enable_cmd_receiving:
            self.cmd_recv_lck = Lock()
            self.cmd_recv_dict = {}
            self.cmd_recv_thread = Thread(target=self.__cmdRecv );
            self.cmd_recv_thread.start()
            self.cmd_recv_thread.setName('sck_cmd_recv'+str(self.com_port))
            print("started new thread [{}] for tcp communication of command data".format(self.cmd_recv_thread.getName()))    
        
        if enable_mass_send:
            self.tcp_buf_lck = Lock()
            self.tcp_buf = []            
            self.massSend_thread = Thread(target=self.__massSend );
            self.massSend_thread.start()
            self.massSend_thread.setName('sck_mass_send_'+str(self.com_port))
            print("started new thread [{}] for tcp mass sending data".format(self.massSend_thread.getName()))

            self.encoder_buf_lck = Lock()
            self.encoder_buf = []
            self.imgEncoder_thread = Thread(target=self.__imgEncoder, args=(send_wide_or_telefocus_img, 100) );
            self.imgEncoder_thread.start()
            self.imgEncoder_thread.setName('img_encoder_'+str(self.com_port))
            print("started new thread [{}] for encoding image data".format(self.imgEncoder_thread.getName()))

    def __del__( self ):
        self.socket_run = False
        self.massSend_thread.join();
        self.cmd_receiving_thread.join();
        if self.new_connection != None:
            self.new_connection.close()
        self.socket_tcp.close()

    def sendCMD( self, cmd, cmd_val ):
        if self.new_connection:
            self.cmd_send_lck.acquire()
            if cmd not in self.cmd_send_dict.keys():
                self.cmd_send_dict[cmd] = []
            self.cmd_send_dict[cmd].append( cmd_val )
            self.cmd_send_lck.release()
        else:
            print("can't send command data, as connection failed!")

    def sendMCStatus( self, status, id, freq ):
        self.sendCMD("mc_status", status+"_"+id+"_"+str(freq)+"hz")
        
    def receiveCMD( self, cmd ):
        cmd_val = None
        self.cmd_recv_lck.acquire()
        if cmd in self.cmd_recv_dict.keys():
            if len( self.cmd_recv_dict[cmd] ) > 0:
                cmd_val = self.cmd_recv_dict[cmd][0]
                self.cmd_recv_dict[cmd].pop(0)
        self.cmd_recv_lck.release()
        return cmd_val

    def sendWideImage( self, img ):
        self.encoder_buf_lck.acquire()
        self.encoder_buf.append( img )
        if len( self.encoder_buf ) % (self.buffer_size*10) == 0 and len( self.encoder_buf ) > 0:
            print("encode wide image buffer overflow:{}".format( len(self.encoder_buf)))
        self.encoder_buf_lck.release();

    def sendPosAndTelefocusImg( self, img, pos ):
        self.encoder_buf_lck.acquire()
        self.encoder_buf.append( [pos, img] )
        if len( self.encoder_buf ) % (self.buffer_size*10) == 0 and len( self.encoder_buf ) > 0:
            print("encode pos and telefocus img buffer overflow:{}".format( len(self.encoder_buf)))
        self.encoder_buf_lck.release();

    def __imgEncoder( self, send_wide_or_telefocus_img, quality ):
        while( self.socket_run ):
            if send_wide_or_telefocus_img:
                self.__encodeWideImage( quality )
            else:
                self.__encodePosAndTelefocusImg( quality )

    def __waitingForConnect( self ):
        #waitting for connecting
        if self.socket_tcp != None:
            self.socket_tcp.close()
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
        # self.socket_tcp.settimeout( 3 )
        print("created socket, target ip:[{}], target port:[{}]".format(self.com_ip, self.com_port))
        self.socket_tcp.bind( ('',self.com_port) )
        self.socket_tcp.listen( 3 )
        print("............listening at ip:[{}] port:[{}]".format(socket.gethostbyname(socket.gethostname()), self.com_port))
        connecton = None; addr = None;
        while self.socket_run:
            try:
                connecton,addr = self.socket_tcp.accept()
                if connecton != socket.error and addr[0] == self.com_ip:
                    print("new connection at port [{}] was found from [{}]".format(self.com_port, addr))    
                    break;
            except socket.timeout:
                pass
            time.sleep( 0.001 )
        return connecton, addr, True

    def __sendData( self, connection, data ):
        connection_ok = True; send_ok = True
        try:
            if not connection.send(data):
                connection_ok = False
        except socket.timeout:
            send_ok = False
        except Exception as ex:
            print("send Data exception: ", ex)
            connection_ok = False;
        return connection_ok, send_ok

    def __recvDataPart( self, connection, data_len ):
        connection_ok = True; recv_ok = True
        recv_len = 0;
        recv_data = b'';
        times_counter = 1000;
        while recv_len < data_len and connection_ok and times_counter > 0:
            try:
                recv_data_temp = connection.recv( data_len )
                if recv_data_temp:
                    recv_len += len( recv_data_temp )
                    recv_data += recv_data_temp
                else:
                    time.sleep( 0.0001 )
                    # print( "recv data part error:", recv_data_temp )
                    # connection_ok = False
                times_counter -= 1
            except socket.timeout:
                pass
            except Exception as ex:
                print("recv data part exception: ",ex)
                connection_ok = False
        
        if times_counter == 0:
            recv_ok = False

        return connection_ok, recv_ok, recv_data

    def __recvData( self, connection ):
        #receiving data_head
        connection_ok, recv_ok, recv_data_head = self.__recvDataPart( connection, self.pkg_head_len )
        if connection_ok == False or recv_ok == False:
            return False, False, None #reset connection

        head_ok = True
        try:
            data_head_decode = recv_data_head.decode("ascii")
        except Exception as ex:
            print("data head decode exception: ",ex)
            head_ok = False
        if head_ok:
            if data_head_decode[:11] != "pkg_length:":
                head_ok = False
        if head_ok == False:
            return False, False, None #reset connection
        
        #receiving data_body
        connection_ok, recv_ok, recv_data = self.__recvDataPart( connection, int( data_head_decode[11:self.pkg_head_len] ) )
        if connection_ok == False or recv_ok == False:
            return False, False, None #reset connection
        return connection_ok, recv_ok, recv_data

    def __sendPkg( self, connection, pkg ):
        connection_ok, send_ok = self.__sendData( connection, pkg )
        if connection_ok == False or send_ok == False:
            return False, False

        #receiving ack
        connection_ok, recv_ok, recv_data = self.__recvData( connection )
        if connection_ok == False or recv_ok == False:
            return False, False

        ack_ok = True
        try:
            recv_ack_decode = recv_data.decode("ascii")
        except Exception as ex:
            print("recv ack data decode exception: ", ex)
            ack_ok = False
        if ack_ok and len( recv_ack_decode ) >= 11:
            if recv_ack_decode[:11] != "response:ok":
                print("response ack error:", recv_ack_decode)
                ack_ok = False
        if ack_ok == False:
            return False, False

        return connection_ok, send_ok

    def __recvPkg( self, connection ):
        #receiving pkg_body
        connection_ok, recv_ok, recv_data = self.__recvData( connection )
        if connection_ok == False or recv_ok == False:
            return False, False, None
        
        #sending response
        ack = "response:ok"
        ack_pkg = self.__package( ack.encode("ascii") )
        connection_ok, send_ok = self.__sendData( connection, ack_pkg )
        if connection_ok == False or send_ok == False:
            return False, False, None

        return connection_ok, recv_ok, recv_data

    def __massSend( self ):
        # send_counter = 0;
        while( self.socket_run ):
            self.new_connection = None
            connection, addr, connection_ok = self.__waitingForConnect()
            if connection_ok:
                self.new_connection = connection
            while connection_ok and self.socket_run:
                pkg = None;
                self.tcp_buf_lck.acquire();
                if len( self.tcp_buf ) > 0:
                    pkg = self.tcp_buf[0]
                    self.tcp_buf.pop(0)
                self.tcp_buf_lck.release();
                if pkg  is not None:
                    #sending package body
                    connection_ok, send_ok = self.__sendPkg( connection, pkg )
                    #for debuging.....
                    # send_counter = send_counter+1
                    # print("send package len:{}, send_counter:{}".format(pkg[:20].decode("ascii"), send_counter))
                else:
                    time.sleep( 0.001 )
                
                if connection_ok == False or self.socket_run == False:
                    connection.close()
                    self.new_connection = None
                    self.socket_tcp.close()
                    self.socket_tcp = None
                    print("connection error at port [{}] occured from [{}], disconnecting......".format(self.com_port, addr))

    def __cmdSend( self ):
        while( self.socket_run ):
            self.new_connection = None
            connection, addr, connection_ok = self.__waitingForConnect()
            if connection_ok:
                self.new_connection = connection
            while connection_ok and self.socket_run:
                #send command data
                send_data = self.__packageControlVars()
                if send_data != None:
                    connection_ok, send_ok = self.__sendPkg( connection, send_data )
                
                if connection_ok == False or self.socket_run == False:
                    connection.close()
                    self.new_connection = None
                    self.socket_tcp.close()
                    print("connection error at port [{}] occured from [{}], disconnecting......".format(self.com_port, addr))

                time.sleep(0.01)

    def __cmdRecv( self ):
        while( self.socket_run ):
            self.new_connection = None
            connection, addr, connection_ok = self.__waitingForConnect()
            if connection_ok:
                self.new_connection = connection
            while connection_ok and self.socket_run:
                #receive command data
                connection_ok, recv_ok, recv_data = self.__recvPkg( connection )
                if connection_ok and recv_ok:
                    self.__parseControlVars( recv_data )

                if connection_ok == False or self.socket_run == False:
                    connection.close()
                    self.new_connection = None
                    self.socket_tcp.close()
                    print("connection error at port [{}] occured from [{}], disconnecting......".format(self.com_port, addr))

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
            img_code = self.turbojpeg.encode( img, self.encode_quality )
            #img_code = self.nj.encode( img , self.encode_quality )
            pkgs = self.__package( img_code )
            self.tcp_buf_lck.acquire();
            if self.new_connection != None:
                self.tcp_buf.append( pkgs )
            if len( self.tcp_buf )  > self.buffer_size:
                print("tcp sending buffer overflow, port: {}, num:{}".format( self.com_port, len(self.tcp_buf)))
                self.tcp_buf.pop(0);
            self.tcp_buf_lck.release();
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
            img_code = self.turbojpeg.encode( img, self.encode_quality )
            #img_code = self.nj.encode( img, self.encode_quality )
            pos_code = json.dumps( pos ).encode("ascii")
            pos_code = self.__alignCompletion( pos_code, 7000 )
            pos_img_code = pos_code + img_code
            pkgs = self.__package( pos_img_code )
            self.tcp_buf_lck.acquire();
            if self.new_connection != None:
                self.tcp_buf.append( pkgs )
            if len(self.tcp_buf) > self.buffer_size:
                print("tcp sending buffer overflow, port: {}, num:{}".format( self.com_port, len(self.tcp_buf)))
                self.tcp_buf.pop(0);
            self.tcp_buf_lck.release();
        else:
            time.sleep( 0.001 )

    # def __parseRevPkgHead( self, pkg, pkg_body ):
    #     pkg_head = json.loads(pkg[:100].decode("ascii"))
    #     received_finished = False
    #     if pkg_head['all_pkgs'] == pkg_head['pkg_index'] + 1:
    #         received_finished = True
        
    #     if receivedself.buffer_size_body = pkg[100:100+pkg_head['last_pkg_len']]
    #         elif pkg_body is not None:
    #             pkg_body = pkg_body + pkg[100:100+pkg_head['last_pkg_len']]
    #     else:
    #         if pkg_head['pkg_index'] == 0:
    #             pkg_body = pkg[100:9100]
    #         elif pkg_body is not None:
    #             pkg_body = pkg_body + pkg[100:9100]

    #     return pkg_body, received_finished

    def __parseControlVars( self, pkg):
        pkg_json = json.loads(pkg.decode("ascii"))
        self.cmd_recv_lck.acquire()
        for k, v in pkg_json.items():
            if k not in self.cmd_recv_dict.keys():
                self.cmd_recv_dict[k] = []
            self.cmd_recv_dict[k].append( v )
        self.cmd_recv_lck.release()

    def __packageControlVars( self ):
        cmd_dict = {}
        self.cmd_send_lck.acquire()
        for k, v in self.cmd_send_dict.items():
            if len( v ) > 0:
                cmd_dict[k] = v[0]
                self.cmd_send_dict[k].pop(0)
        self.cmd_send_lck.release()
        
        if not cmd_dict:
            return None
        
        return self.__package( json.dumps( cmd_dict ).encode("ascii"))

    def __package( self, pkg_body ):
        pkg_len = ("pkg_length:"+str(len(pkg_body))).encode("ascii")
        pkg_len = self.__alignCompletion( pkg_len, self.pkg_head_len )
        package = pkg_len + pkg_body
        return package

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
    def __init__(self, ip, port, enable_mass_receive=False, receive_wide_or_telefocus_img=False, enable_cmd_receiving=False, enable_cmd_sending=False, encode_quality = 100) -> None:
        self.socket_run = True
        self.socket_tcp = None
        self.connect_to_sever_flag = False
        self.com_ip = ip
        self.com_port = port
        self.encode_quality = encode_quality
        self.buffer_size = 3
        self.pkg_head_len = 20
        self.turbojpeg = TurboJPEG()
        # self.nj = NvJpeg()

        if enable_mass_receive + enable_cmd_sending + enable_cmd_receiving > 1:
            print("error: init CBackEndSocket")

        if enable_cmd_sending:
            self.cmd_send_lck = Lock()
            self.cmd_send_dict = {}
            self.cmd_send_thread = Thread(target=self.__cmdSend );
            self.cmd_send_thread.start()
            self.cmd_send_thread.setName('sck_cmd_send'+str(self.com_port))
            print("started new thread [{}] for tcp communication of command data".format(self.cmd_send_thread.getName()))    
        
        if enable_cmd_receiving:
            self.cmd_recv_lck = Lock()
            self.cmd_recv_dict = {}
            self.cmd_recv_thread = Thread(target=self.__cmdRecv );
            self.cmd_recv_thread.start()
            self.cmd_recv_thread.setName('sck_cmd_recv'+str(self.com_port))
            print("started new thread [{}] for tcp communication of command data".format(self.cmd_recv_thread.getName()))    
        
        if enable_mass_receive:
            self.pkgs_buf_lck = Lock()
            self.pkgs_buf = []
            self.massReceive_thread = Thread(target=self.__massReceive );
            self.massReceive_thread.start()
            self.massReceive_thread.setName('sck_mass_rev_'+str(self.com_port))
            print("started new thread [{}] for tcp mass receiving data".format(self.massReceive_thread.getName()))

            self.decoder_buf_lck = Lock()
            self.decoder_buf = []
            self.imgDecoder_thread = Thread(target=self.__imgDecoder, args=(receive_wide_or_telefocus_img,) );
            self.imgDecoder_thread.start()
            self.imgDecoder_thread.setName('img_decoder_'+str(self.com_port))
            print("started new thread [{}] for decoding image data".format(self.imgDecoder_thread.getName()))
            

    def __del__( self ):
        self.socket_run = False
        self.massReceive_thread.join();
        self.cmd_receiving_thread.join();
        self.socket_tcp.close()

    def sendCMD( self, cmd, cmd_val ):
        if self.connect_to_sever_flag:
            self.cmd_send_lck.acquire()
            if cmd not in self.cmd_send_dict.keys():
                self.cmd_send_dict[cmd] = []
            self.cmd_send_dict[cmd].append( cmd_val )
            self.cmd_send_lck.release()
        else:
            print("can't send command data, as connection failed!")
 
    def receiveCMD( self, cmd ):
        cmd_val = None
        self.cmd_recv_lck.acquire()
        if cmd in self.cmd_recv_dict.keys():
            if len( self.cmd_recv_dict[cmd] ) > 0:
                cmd_val = self.cmd_recv_dict[cmd][0]
                self.cmd_recv_dict[cmd].pop(0)
        self.cmd_recv_lck.release()
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

    def __connectToSever( self ):
        if self.socket_tcp != None:
            self.socket_tcp.close()
        self.socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        self.socket_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
        # self.socket_tcp.settimeout( 3 )
        print("created socket, target ip:[{}], target port:[{}]".format(self.com_ip, self.com_port))

        #trying to connecting server
        connection_ok = False;
        try_connect_counter = 0
        while try_connect_counter < 200:
            try:
                conn_status = self.socket_tcp.connect((self.com_ip, self.com_port))
                if conn_status != socket.error:
                    connection_ok = True;
                    print("connecting to ip:{}, port:{} successfully".format(self.com_ip, self.com_port))
                    try_connect_counter = 201
                else:
                    self.socket_tcp.close()
                    print("try connecting to ip:{}, port:{} Failed! tried [{}] times again".format(self.com_ip, self.com_port, try_connect_counter))                    
            except Exception as ex:
                print("try connecting to ip:{}, port:{} Exception:{} ! tried [{}] times again".format(self.com_ip, self.com_port, ex, try_connect_counter))
            time.sleep(1)
            try_connect_counter += 1;
        
        return connection_ok

    def __sendData( self, connection, data ):
        connection_ok = True; send_ok = True
        try:
            if not connection.send(data):
                connection_ok = False
        except socket.timeout:
            send_ok = False
        except Exception as ex:
            print("send Data exception: ", ex)
            connection_ok = False;
        return connection_ok, send_ok

    def __recvDataPart( self, connection, data_len ):
        connection_ok = True; recv_ok = True
        recv_len = 0;
        recv_data = b'';
        times_counter = 1000;
        while recv_len < data_len and connection_ok and times_counter > 0:
            try:
                recv_data_temp = connection.recv( data_len )
                if recv_data_temp:
                    recv_len += len( recv_data_temp )
                    recv_data += recv_data_temp
                else:
                    time.sleep( 0.0001 )
                    # print( "recv data part error:", recv_data_temp )
                    # connection_ok = False
                times_counter -= 1
            except socket.timeout:
                pass
            except Exception as ex:
                print("recv data part exception: ",ex)
                connection_ok = False
        
        if times_counter == 0:
            recv_ok = False

        return connection_ok, recv_ok, recv_data

    def __recvData( self, connection ):
        #receiving data_head
        connection_ok, recv_ok, recv_data_head = self.__recvDataPart( connection, self.pkg_head_len )
        if connection_ok == False or recv_ok == False:
            return False, False, None #reset connection

        head_ok = True
        try:
            data_head_decode = recv_data_head.decode("ascii")
        except Exception as ex:
            print("data head decode exception: ",ex)
            head_ok = False
        if head_ok:
            if data_head_decode[:11] != "pkg_length:":
                head_ok = False
        if head_ok == False:
            return False, False, None #reset connection
        
        #receiving data_body
        connection_ok, recv_ok, recv_data = self.__recvDataPart( connection, int( data_head_decode[11:self.pkg_head_len] ) )
        if connection_ok == False or recv_ok == False:
            return False, False, None #reset connection
        return connection_ok, recv_ok, recv_data

    def __sendPkg( self, connection, pkg ):
        connection_ok, send_ok = self.__sendData( connection, pkg )
        if connection_ok == False or send_ok == False:
            return False, False

        #receiving ack
        connection_ok, recv_ok, recv_data = self.__recvData( connection )
        if connection_ok == False or recv_ok == False:
            return False, False

        ack_ok = True
        try:
            recv_ack_decode = recv_data.decode("ascii")
        except Exception as ex:
            print("recv ack data decode exception: ", ex)
            ack_ok = False
        if ack_ok and len( recv_ack_decode ) >= 11:
            if recv_ack_decode[:11] != "response:ok":
                print("response ack error:", recv_ack_decode)
                ack_ok = False
        if ack_ok == False:
            return False, False

        return connection_ok, send_ok

    def __recvPkg( self, connection ):
        #receiving pkg_body
        connection_ok, recv_ok, recv_data = self.__recvData( connection )
        if connection_ok == False or recv_ok == False:
            return False, False, None
        
        #sending response
        ack = "response:ok"
        ack_pkg = self.__package( ack.encode("ascii") )
        connection_ok, send_ok = self.__sendData( connection, ack_pkg )
        if connection_ok == False or send_ok == False:
            return False, False, None

        return connection_ok, recv_ok, recv_data

    def __massReceive( self ):
        # recv_counter = 0;
        while self.socket_run:
            self.connect_to_sever_flag = False
            connection_ok = self.__connectToSever()
            if connection_ok:
                self.connect_to_sever_flag = True
            while self.socket_run and connection_ok :
                #receiving package size
                connection_ok, recv_ok, package = self.__recvPkg( self.socket_tcp )           
                #receive package body
                if connection_ok and recv_ok:
                    self.pkgs_buf_lck.acquire()
                    self.pkgs_buf.append( package )
                    if len(self.pkgs_buf) % 100 == 0 and len(self.pkgs_buf) > 0:
                        print("rev pkgs_buf overflow: ", len(self.pkgs_buf))
                    self.pkgs_buf_lck.release()
                    #for debuging......
                    # recv_counter += 1;
                    # print(" received package over! recv_counter:", recv_counter)

                if connection_ok == False or self.socket_run == False:
                    self.socket_tcp.close()
                    self.socket_tcp = None
                    print( "connection with ip:{}, port:{} error! disconnecting......".format(self.com_ip, self.com_port ) )

    def __cmdSend( self ):
        while self.socket_run:
            self.connect_to_sever_flag = False
            connection_ok = self.__connectToSever()
            if connection_ok:
                self.connect_to_sever_flag = True
            while self.socket_run and connection_ok :
                #send command data
                send_data = self.__packageControlVars()
                if send_data != None:
                    connection_ok, send_ok = self.__sendPkg( self.socket_tcp, send_data )
                
                if connection_ok == False or self.socket_run == False:
                    self.socket_tcp.close()
                    self.socket_tcp = None
                    print( "connection with ip:{}, port:{} error! disconnecting......".format(self.com_ip, self.com_port ) )

                time.sleep(0.01)
                
    def __cmdRecv( self ):
        while self.socket_run:
            self.connect_to_sever_flag = False
            connection_ok = self.__connectToSever()
            if connection_ok:
                self.connect_to_sever_flag = True
            while self.socket_run and connection_ok :
                #receive command data
                connection_ok, recv_ok, recv_data = self.__recvPkg( self.socket_tcp )
                if connection_ok and recv_ok:
                    self.__parseControlVars( recv_data )

                if connection_ok == False or self.socket_run == False:
                    self.socket_tcp.close()
                    self.socket_tcp = None
                    print( "connection with ip:{}, port:{} error! disconnecting......".format(self.com_ip, self.com_port ) )

    def __imgDecoder(self, receive_wide_or_telefocus_img):
        while( self.socket_run ):
            if receive_wide_or_telefocus_img:
                self.__decodeWideImage(  )
            else:
                self.__decodePosAndTelefocusImg(  )
            
    def __decodeWideImage( self ):
        img_code = None
        #read from buffer
        self.pkgs_buf_lck.acquire()
        if len(self.pkgs_buf) > 0:
            img_code = self.pkgs_buf[0]
            self.pkgs_buf.pop(0)
        self.pkgs_buf_lck.release()

        if img_code is not None:
            #img_code = np.frombuffer( img_code, dtype = "uint8" )
            #img = cv2.imdecode( img_code, cv2.IMREAD_COLOR )
            img = self.turbojpeg.decode( img_code, pixel_format=TJPF_BGR )
            #img = self.nj.decode( img_code )
            self.decoder_buf_lck.acquire()
            self.decoder_buf.append( img )
            if len( self.decoder_buf )  > self.buffer_size :
                print("decode wide image buffer overflow:{}".format( len(self.decoder_buf)))
                self.decoder_buf.pop(0)
            self.decoder_buf_lck.release( )
        else:
            sleep( 0.0001 )

    def __decodePosAndTelefocusImg( self ):
        pos_img_code = None
        #read from buffer
        self.pkgs_buf_lck.acquire()
        if len(self.pkgs_buf) > 0:
            pos_img_code = self.pkgs_buf[0]
            self.pkgs_buf.pop(0)
        self.pkgs_buf_lck.release()

        if pos_img_code is not None:
            #img_code = np.frombuffer( img_code, dtype = "uint8" )
            #img = cv2.imdecode( img_code, cv2.IMREAD_COLOR )
            img = self.turbojpeg.decode( pos_img_code[7000:], pixel_format=TJPF_BGR)
            #img = self.nj.decode( pos_img_code[7000:] )
            pos_code = pos_img_code[:7000].decode("ascii")
            pos = json.loads(pos_code)
            self.decoder_buf_lck.acquire()
            self.decoder_buf.append( [pos, img] )
            if len( self.decoder_buf ) > self.buffer_size:
                print("decode pos_telefocus image buffer overflow:{}".format( len(self.decoder_buf)))
                self.decoder_buf.pop(0)
            self.decoder_buf_lck.release( )
        else:
            sleep( 0.0001 )

    # def __parseRevPkgHead( self, pkg, pkg_body ):
    #     pkg_head = json.loads(pkg[:100].decode("ascii"))
    #     received_finished = False
    #     if pkg_head['all_pkgs'] == pkg_head['pkg_index'] + 1:
    #         received_finished = True
        
    #     if received_finished:
    #         if pkg_head['pkg_index'] == 0:
    #             pkg_body = pkg[100:100+pkg_head['last_pkg_len']]
    #         elif pkg_body is not None:
    #             pkg_body = pkg_body + pkg[100:100+pkg_head['last_pkg_len']]
    #     else:
    #         if pkg_head['pkg_index'] == 0:
    #             pkg_body = pkg[100:9100]
    #         elif pkg_body is not None:
    #             pkg_body = pkg_body + pkg[100:9100]

    #     return pkg_body, received_finished
    
    def __parseControlVars( self, pkg):
        pkg_json = json.loads(pkg.decode("ascii"))
        self.cmd_recv_lck.acquire()
        for k, v in pkg_json.items():
            if k not in self.cmd_recv_dict.keys():
                self.cmd_recv_dict[k] = []
            self.cmd_recv_dict[k].append( v )
        self.cmd_recv_lck.release()

    def __packageControlVars( self ):
        cmd_dict = {}
        self.cmd_send_lck.acquire()
        for k, v in self.cmd_send_dict.items():
            if len( v ) > 0:
                cmd_dict[k] = v[0]
                self.cmd_send_dict[k].pop(0)
        self.cmd_send_lck.release()
        
        if not cmd_dict:
            return None
        
        return self.__package( json.dumps( cmd_dict ).encode("ascii") )

    def __package( self, pkg_body ):
        pkg_len = ("pkg_length:"+str(len(pkg_body))).encode("ascii")
        pkg_len = self.__alignCompletion( pkg_len, self.pkg_head_len )
        package = pkg_len + pkg_body
        return package

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

    wide_img_sck =       CAlogrithmSocket(host_ip, communication_port, True, True, False, False )
    telefocus_img_sck =  CAlogrithmSocket(host_ip, communication_port+3, True, False, False, False )
    cmd_sck_send =  CAlogrithmSocket(host_ip, communication_port+1, False, False, False, True )
    cmd_sck_recv =  CAlogrithmSocket(host_ip, communication_port+2, False, False, True, False )

    run_freq = 40 #40fps
    galvos_num = 2

    mc_mode = "automation"
    mc_triger="finish" 
    mc_tracker=[0,0]
    mc_status="finished"
    mc_playback="disable"
    mc_id = ""
    record_freq = 35

    cv2.namedWindow("cam_Wide_Send",0)
    cv2.namedWindow("cam_Telefocus_Send",0)

    wide_img = np.zeros((1080,1920*galvos_num, 3), np.uint8)
    telefocus_img = np.zeros((1080, 1440*galvos_num, 3), np.uint8)
    wide_img = np.random.randint( 255, size=wide_img.shape, dtype=np.uint8 )
    telefocus_img = np.random.randint( 255, size=telefocus_img.shape, dtype=np.uint8 )
    pos_num = 0
    play_back_counter = 0;
    while( True ):
        cmd = cmd_sck_recv.receiveCMD( "mc_mode" )
        if cmd is not None:
            mc_mode = cmd
            print("get mc_mode: ",mc_mode)

        cmd = cmd_sck_recv.receiveCMD( "mc_playback" )
        if cmd is not None:
            mc_playback = cmd
            print("get mc_playback: ",mc_playback)

        cmd = cmd_sck_recv.receiveCMD( "mc_triger" )
        if cmd is not None and play_back_counter == 0:
            mc_triger = cmd
            print("get mc_triger: ",mc_triger)
            if mc_triger == "start":
                mc_status = "start"
                mc_id = time.strftime("%Y_%m_%d_%H_%M_%S")
                record_freq = 35
                cmd_sck_send.sendMCStatus( mc_status, mc_id, record_freq )
            elif mc_triger == "finish":
                mc_status = "finished"
                cmd_sck_send.sendMCStatus( copy.deepcopy(mc_status), copy.deepcopy(mc_id), copy.deepcopy(record_freq) )
                if mc_playback == "enable":
                    time.sleep(0.1)
                    play_back_counter = play_back_counter + 1
                    mc_status = "start"
                    mc_id = "p_" + mc_id
                    record_freq = 100
                    cmd_sck_send.sendMCStatus( mc_status, mc_id, record_freq )

        if play_back_counter > 0:
            play_back_counter = play_back_counter + 1
            if play_back_counter > 1000:
                play_back_counter = 0
                mc_status = "finished"
                cmd_sck_send.sendMCStatus( mc_status, mc_id, record_freq )

        cmd = cmd_sck_recv.receiveCMD( "mc_tracker" )
        if cmd is not None:
            mc_tracker = cmd
            print("get mc_tracker: ",mc_tracker)

        send_wide_img  = cv2.putText(wide_img.copy(), str(time.time()), (600, 1000), cv2.FONT_HERSHEY_SIMPLEX, 6.0, (255,255,255), 2)
        send_telefocus_img  = cv2.putText(telefocus_img.copy(), str(time.time()), (300, 500), cv2.FONT_HERSHEY_SIMPLEX, 6.0, (255,255,255), 2)
        pos_num = pos_num + 1
        if pos_num > 1000:
            pos_num = 0
        pos = {"pose_world":[{"x":i+pos_num,"y":i+pos_num+1, "z":i+pos_num+2 } for i in range(18)] }
        for galvo_index in range(galvos_num):
            pos.update({"pose_reprojection_"+str(galvo_index):[{"x":(i+pos_num+galvo_index)/1050.0, "y":(i+pos_num+galvo_index)/1050.0} for i in range(18)]})
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
