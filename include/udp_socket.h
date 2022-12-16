#include <sys/select.h>
#include <sys/time.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <cstdlib>
#include <cstdio>
#include <string.h>
#include <iostream>
#include <deque>
#include <thread>

#define  MAX_UDP_BUFFER 1000

using namespace std;

class CTIMERDEBUG
{
public:
    CTIMERDEBUG( string timer_name_, int print_freq_=100 )
    {
        counter_times = 0;
        spent_time = 0;
        print_freq = print_freq_;
        timer_name = timer_name_;
        gettimeofday(&timer_last, NULL);
    };

    void timer_start( void )
    {
        gettimeofday(&timer_last, NULL);
    };

    void timer_end( void )
    {
        struct timeval current_time;
        gettimeofday(&current_time, NULL);
        spent_time = spent_time + (current_time.tv_sec * 1000000 + current_time.tv_usec) -
                        (timer_last.tv_sec * 1000000 + timer_last.tv_usec);
        counter_times++;
    };

    void print_timer()
    {
        if( counter_times >= print_freq )
        {
            double avarage_spent = double(spent_time)/double(counter_times);
            counter_times = 0;
            spent_time = 0;
            printf("timer [%s] avarage time:[%f] ms [%f] HZ\n",timer_name.c_str(),  avarage_spent/1000.0, 1000000.0/avarage_spent );
        }
    }

private:
    struct timeval timer_last;
    long spent_time;
    int  counter_times;
    int  print_freq;
    string timer_name;
};

typedef struct PkgBody
{
    PkgBody( int pkg_bdy_size_ )
    {
        pkg_bdy_size = pkg_bdy_size_;
        pkg_bdy_size_counter = 0;
        pkg_bdy = new char[pkg_bdy_size]();
    }
    char * pkg_bdy;
    int pkg_bdy_size;
    int pkg_bdy_size_counter;
};


extern "C"
{   
    void massReceiving( int port, int pkg_size );

    unsigned char * readPkgBdy( int * len );

    void   delPkgBdy( void );

    void  stopReceiving( );
}