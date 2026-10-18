/* Exercise the real pinned controller with its synthetic-sector fixture. */
#define main upstream_fifo_tests
#include "test_cdrom_sector_fifo.c"
#undef main

static void explicit_seek_stops_stream(uint8_t command, uint8_t read_command) {
    setup();
    stat_reg = CDSTAT_MOTOR | CDSTAT_READ;
    seek_min = 0; seek_sec = 4; seek_sect = 0;
    exec_command(command);
    CHECK(!reading && !cdda_playing);
    CHECK((stat_reg & (CDSTAT_SEEK | CDSTAT_READ | CDSTAT_PLAY)) == CDSTAT_SEEK);
    CHECK(irq_flag == CDIRQ_ACK);
    ack();
    psx_cycle_count = pending.due_cyc;
    process_pending(0);
    CHECK(irq_flag == CDIRQ_COMPLETE);
    CHECK((stat_reg & (CDSTAT_SEEK | CDSTAT_READ | CDSTAT_PLAY)) == 0);
    CHECK(stat_reg & CDSTAT_MOTOR);
    ack();
    exec_command(0x01); /* Repeated Getstat must report the idle drive. */
    CHECK(!(stat_reg & CDSTAT_READ));
    ack();
    exec_command(read_command);
    CHECK(reading && (stat_reg & CDSTAT_READ));
    CHECK(!(stat_reg & (CDSTAT_SEEK | CDSTAT_PLAY)));
}

int main(void) {
    upstream_fifo_tests();
    explicit_seek_stops_stream(0x15, 0x06); /* SeekL, then ReadN */
    explicit_seek_stops_stream(0x16, 0x1B); /* SeekP, then ReadS */
    puts("PASS: explicit seeks finish idle; subsequent reads resume normally");
    return 0;
}
