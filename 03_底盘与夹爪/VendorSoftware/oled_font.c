#include <stdint.h>
#include <string.h>
void Oled_GetGlyph(char ch,
                          uint8_t glyph[5])
{
    memset(glyph, 0, 5U);

    /*
     * 将小写字母转换成大写。
     */
    if (ch >= 'a' && ch <= 'z')
    {
        ch = (char)(ch - 'a' + 'A');
    }

    switch (ch)
    {
        case '0':
            glyph[0] = 0x3E;
            glyph[1] = 0x51;
            glyph[2] = 0x49;
            glyph[3] = 0x45;
            glyph[4] = 0x3E;
            break;

        case '1':
            glyph[0] = 0x00;
            glyph[1] = 0x42;
            glyph[2] = 0x7F;
            glyph[3] = 0x40;
            glyph[4] = 0x00;
            break;

        case '2':
            glyph[0] = 0x42;
            glyph[1] = 0x61;
            glyph[2] = 0x51;
            glyph[3] = 0x49;
            glyph[4] = 0x46;
            break;

        case '3':
            glyph[0] = 0x21;
            glyph[1] = 0x41;
            glyph[2] = 0x45;
            glyph[3] = 0x4B;
            glyph[4] = 0x31;
            break;

        case '4':
            glyph[0] = 0x18;
            glyph[1] = 0x14;
            glyph[2] = 0x12;
            glyph[3] = 0x7F;
            glyph[4] = 0x10;
            break;

        case '5':
            glyph[0] = 0x27;
            glyph[1] = 0x45;
            glyph[2] = 0x45;
            glyph[3] = 0x45;
            glyph[4] = 0x39;
            break;

        case '6':
            glyph[0] = 0x3C;
            glyph[1] = 0x4A;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x30;
            break;

        case '7':
            glyph[0] = 0x01;
            glyph[1] = 0x71;
            glyph[2] = 0x09;
            glyph[3] = 0x05;
            glyph[4] = 0x03;
            break;

        case '8':
            glyph[0] = 0x36;
            glyph[1] = 0x49;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x36;
            break;

        case '9':
            glyph[0] = 0x06;
            glyph[1] = 0x49;
            glyph[2] = 0x49;
            glyph[3] = 0x29;
            glyph[4] = 0x1E;
            break;

        case 'A':
            glyph[0] = 0x7E;
            glyph[1] = 0x11;
            glyph[2] = 0x11;
            glyph[3] = 0x11;
            glyph[4] = 0x7E;
            break;

        case 'B':
            glyph[0] = 0x7F;
            glyph[1] = 0x49;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x36;
            break;

        case 'C':
            glyph[0] = 0x3E;
            glyph[1] = 0x41;
            glyph[2] = 0x41;
            glyph[3] = 0x41;
            glyph[4] = 0x22;
            break;

        case 'D':
            glyph[0] = 0x7F;
            glyph[1] = 0x41;
            glyph[2] = 0x41;
            glyph[3] = 0x22;
            glyph[4] = 0x1C;
            break;

        case 'E':
            glyph[0] = 0x7F;
            glyph[1] = 0x49;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x41;
            break;

        case 'F':
            glyph[0] = 0x7F;
            glyph[1] = 0x09;
            glyph[2] = 0x09;
            glyph[3] = 0x09;
            glyph[4] = 0x01;
            break;

        case 'G':
            glyph[0] = 0x3E;
            glyph[1] = 0x41;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x7A;
            break;

        case 'I':
            glyph[0] = 0x00;
            glyph[1] = 0x41;
            glyph[2] = 0x7F;
            glyph[3] = 0x41;
            glyph[4] = 0x00;
            break;

        case 'K':
            glyph[0] = 0x7F;
            glyph[1] = 0x08;
            glyph[2] = 0x14;
            glyph[3] = 0x22;
            glyph[4] = 0x41;
            break;

        case 'L':
            glyph[0] = 0x7F;
            glyph[1] = 0x40;
            glyph[2] = 0x40;
            glyph[3] = 0x40;
            glyph[4] = 0x40;
            break;

        case 'M':
            glyph[0] = 0x7F;
            glyph[1] = 0x02;
            glyph[2] = 0x0C;
            glyph[3] = 0x02;
            glyph[4] = 0x7F;
            break;

        case 'N':
            glyph[0] = 0x7F;
            glyph[1] = 0x04;
            glyph[2] = 0x08;
            glyph[3] = 0x10;
            glyph[4] = 0x7F;
            break;

        case 'O':
            glyph[0] = 0x3E;
            glyph[1] = 0x41;
            glyph[2] = 0x41;
            glyph[3] = 0x41;
            glyph[4] = 0x3E;
            break;

        case 'P':
            glyph[0] = 0x7F;
            glyph[1] = 0x09;
            glyph[2] = 0x09;
            glyph[3] = 0x09;
            glyph[4] = 0x06;
            break;

        case 'R':
            glyph[0] = 0x7F;
            glyph[1] = 0x09;
            glyph[2] = 0x19;
            glyph[3] = 0x29;
            glyph[4] = 0x46;
            break;

        case 'S':
            glyph[0] = 0x46;
            glyph[1] = 0x49;
            glyph[2] = 0x49;
            glyph[3] = 0x49;
            glyph[4] = 0x31;
            break;

        case 'T':
            glyph[0] = 0x01;
            glyph[1] = 0x01;
            glyph[2] = 0x7F;
            glyph[3] = 0x01;
            glyph[4] = 0x01;
            break;

        case 'U':
            glyph[0] = 0x3F;
            glyph[1] = 0x40;
            glyph[2] = 0x40;
            glyph[3] = 0x40;
            glyph[4] = 0x3F;
            break;

        case 'V':
            glyph[0] = 0x1F;
            glyph[1] = 0x20;
            glyph[2] = 0x40;
            glyph[3] = 0x20;
            glyph[4] = 0x1F;
            break;

        case 'W':
            glyph[0] = 0x3F;
            glyph[1] = 0x40;
            glyph[2] = 0x38;
            glyph[3] = 0x40;
            glyph[4] = 0x3F;
            break;

        case 'X':
            glyph[0] = 0x63;
            glyph[1] = 0x14;
            glyph[2] = 0x08;
            glyph[3] = 0x14;
            glyph[4] = 0x63;
            break;

        case 'Y':
            glyph[0] = 0x07;
            glyph[1] = 0x08;
            glyph[2] = 0x70;
            glyph[3] = 0x08;
            glyph[4] = 0x07;
            break;

        case 'Z':
            glyph[0] = 0x61;
            glyph[1] = 0x51;
            glyph[2] = 0x49;
            glyph[3] = 0x45;
            glyph[4] = 0x43;
            break;

        case ':':
            glyph[0] = 0x00;
            glyph[1] = 0x36;
            glyph[2] = 0x36;
            glyph[3] = 0x00;
            glyph[4] = 0x00;
            break;

        case '+':
            glyph[0] = 0x08;
            glyph[1] = 0x08;
            glyph[2] = 0x3E;
            glyph[3] = 0x08;
            glyph[4] = 0x08;
            break;

        case '-':
            glyph[0] = 0x08;
            glyph[1] = 0x08;
            glyph[2] = 0x08;
            glyph[3] = 0x08;
            glyph[4] = 0x08;
            break;

        case 'H': { const uint8_t v[5]={0x7f,8,8,8,0x7f};memcpy(glyph,v,5);break; }
        case '/': { const uint8_t v[5]={0x20,0x10,8,4,2};memcpy(glyph,v,5);break; }
        case '.': glyph[1]=glyph[2]=0x60;break;
        case ' ':
        default:
            break;
    }
}
