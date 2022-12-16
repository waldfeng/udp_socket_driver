#include <udp_socket.h>
#include <signal.h>

void signalKillInt(int sig)
{   
    cout<<"Emegency Quit Signal:"<<sig<<endl;
    stopReceiving();
}

int main( int argc,char **argv ) 
{   
    signal( SIGINT, signalKillInt );
    int com_port = 6000;
    if( argc > 1 )
    {
        com_port = stoi(argv[1]);
    }
    int pkg_size = 9100;
    if( argc > 2 )
    {
        pkg_size = stoi(argv[2]);
    }
    massReceiving( com_port, pkg_size );

    return 0;
}

