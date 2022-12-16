#include <udp_socket.h>
#include <jsoncpp/json/json.h>

bool socket_run_flag = false;
deque<shared_ptr<PkgBody>> pkg_bdy_buffer;

void massReceiving( int port, int pkg_size )
{
    socket_run_flag = true;

    CTIMERDEBUG timer_debug("timer_debug", 3000);
    timer_debug.timer_start();

    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if(-1==sockfd)
    {
        puts("Failed to create socket");
        return;
    }

    struct sockaddr_in addr;
    socklen_t addr_len = sizeof(addr);
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    
    struct sockaddr_in addr_src;
    socklen_t addr_src_len = sizeof(addr_src);
    memset(&addr_src, 0, sizeof(addr_src));

    // Time out
    struct timeval tv;
    tv.tv_sec  = 0;
    tv.tv_usec = 200000;  // 200ms
    setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(struct timeval));

    // Bind port
    if (bind(sockfd, (struct sockaddr*)&addr, addr_len) == -1)
    {
        printf("Failed to bind socket on port %d\n", port);
        close(sockfd);
        return;
    }

    char pkg_buffer[pkg_size];
    shared_ptr<PkgBody> pkg_body_ptr;

    Json::Reader reader;
    while( socket_run_flag )
    {
        int sz = recvfrom(sockfd, pkg_buffer, pkg_size, 0, (sockaddr*)&addr_src, &addr_src_len);
        if (sz > 0)
        {   //received pkg
            char pkg_head[100];
            memcpy( pkg_head, pkg_buffer, sizeof(char)*100 );

            Json::Value head_json;
            if (!reader.parse(pkg_head, head_json)) continue;
            
            //parseRevPkgHead
            int all_pkgs = head_json["all_pkgs"].asInt();
            int pkg_index = head_json["pkg_index"].asInt();
            int last_pkg_len = head_json["last_pkg_len"].asInt();
            int pkg_body_size = (all_pkgs - 1)*(pkg_size-100) + last_pkg_len;
            if( pkg_index == 0 )
            {   
                //cout<<"all_pkgs: "<<all_pkgs<<" pkg_index:" <<pkg_index<<" last_pkg_len:"<<last_pkg_len <<" port:"<<port<<endl;
                pkg_body_ptr.reset();
                pkg_body_ptr = make_shared<PkgBody>( pkg_body_size );
            }
            
            if( all_pkgs == ( pkg_index + 1) )
            {   
                if( pkg_body_ptr != NULL )
                {   
                    if( (pkg_index*(pkg_size-100)+last_pkg_len) <= pkg_body_ptr->pkg_bdy_size )
                    {
                        memcpy( pkg_body_ptr->pkg_bdy+pkg_index*(pkg_size-100), pkg_buffer+100, sizeof(char)*last_pkg_len);
                        pkg_body_ptr->pkg_bdy_size_counter = pkg_body_ptr->pkg_bdy_size_counter + last_pkg_len;

                        pkg_bdy_buffer.push_back( pkg_body_ptr );
                        if( pkg_bdy_buffer.size() > MAX_UDP_BUFFER )
                        {
                            cout<<"packages body buffer over flow:["<<pkg_bdy_buffer.size()<<"]"<<endl;
                            delete [] pkg_bdy_buffer.front()->pkg_bdy;
                            pkg_bdy_buffer.front().reset();
                            pkg_bdy_buffer.pop_front();
                        }
                    }
                    else
                    {
                        delete [] pkg_body_ptr->pkg_bdy;
                    }
                    pkg_body_ptr.reset();
                }
            }
            else
            {   
                if( pkg_body_ptr != NULL )
                {   
                    if( ((pkg_index+1)*(pkg_size-100)) <= pkg_body_ptr->pkg_bdy_size )
                    {
                        memcpy( pkg_body_ptr->pkg_bdy+pkg_index*(pkg_size-100), pkg_buffer+100, sizeof(char)*(pkg_size-100));
                        pkg_body_ptr->pkg_bdy_size_counter = pkg_body_ptr->pkg_bdy_size_counter + pkg_size-100 ;
                    }
                }
            }

            if ( false )
            {
                timer_debug.timer_end();
                timer_debug.print_timer();
                timer_debug.timer_start();
            }
        }
    }

    close(sockfd);
}
    
unsigned char * readPkgBdy( int * len )
{   
    unsigned char * pkg_bdy = NULL;
    *len = 0;

    if( pkg_bdy_buffer.size() > 0 )
    {   
        pkg_bdy = reinterpret_cast<unsigned char *>(pkg_bdy_buffer.front()->pkg_bdy);
        *len = pkg_bdy_buffer.front()->pkg_bdy_size;
    }

    return pkg_bdy;
}

void delPkgBdy( void )
{   
    if( pkg_bdy_buffer.size() > 0 )
    {
        delete [] pkg_bdy_buffer.front()->pkg_bdy;
        pkg_bdy_buffer.front().reset();
        pkg_bdy_buffer.pop_front();
    }
}

void  stopReceiving( )
{
    socket_run_flag = false;
    while( pkg_bdy_buffer.size( ) > 0 )
    {   
        delete [] pkg_bdy_buffer.front()->pkg_bdy;
        pkg_bdy_buffer.front().reset();
        pkg_bdy_buffer.pop_front();
    }
}
