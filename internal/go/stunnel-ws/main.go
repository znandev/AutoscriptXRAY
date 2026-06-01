package main

import (
	"bufio"
	"fmt"
	"io"
	"log"
	"net"
	"strings"
)

const (
	ListenAddr = "0.0.0.0:2096"
	DefaultHost = "127.0.0.1:109"
	Password = ""
)

var Response = []byte(
	"HTTP/1.1 101 Znandxyz Server Connected\r\n" +
		"Content-Length: 104857600000\r\n" +
		"\r\n",
)

func main() {
	ln, err := net.Listen("tcp", ListenAddr)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("WS-Stunnel listening on %s", ListenAddr)

	for {
		conn, err := ln.Accept()
		if err != nil {
			continue
		}

		go handle(conn)
	}
}

func handle(client net.Conn) {
	defer client.Close()

	reader := bufio.NewReader(client)

	var headers []string

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}

		headers = append(headers, line)

		if line == "\r\n" {
			break
		}
	}

	rawHeader := strings.Join(headers, "")

	hostPort := getHeader(rawHeader, "X-Real-Host")

	if hostPort == "" {
		hostPort = DefaultHost
	}

	pass := getHeader(rawHeader, "X-Pass")

	if Password != "" && pass != Password {
		client.Write([]byte("HTTP/1.1 400 WrongPass!\r\n\r\n"))
		return
	}

	if !strings.HasPrefix(hostPort, "127.0.0.1") &&
		!strings.HasPrefix(hostPort, "localhost") {
		client.Write([]byte("HTTP/1.1 403 Forbidden!\r\n\r\n"))
		return
	}

	target, err := net.Dial("tcp", hostPort)
	if err != nil {
		return
	}
	defer target.Close()

	log.Printf(
		"CONNECT %s <- %s",
		client.RemoteAddr(),
		hostPort,
	)

	_, err = client.Write(Response)
	if err != nil {
		return
	}

	go func() {
		_, _ = io.Copy(target, reader)
		if tcp, ok := target.(*net.TCPConn); ok {
			_ = tcp.CloseWrite()
		}
	}()

	_, _ = io.Copy(client, target)

	log.Printf(
		"DISCONNECT %s",
		client.RemoteAddr(),
	)
}

func getHeader(raw string, key string) string {
	for _, line := range strings.Split(raw, "\r\n") {

		if strings.HasPrefix(
			strings.ToLower(line),
			strings.ToLower(key)+":",
		) {

			parts := strings.SplitN(
				line,
				":",
				2,
			)

			if len(parts) != 2 {
				return ""
			}

			return strings.TrimSpace(parts[1])
		}
	}

	return ""
}

func init() {
	fmt.Println("")
	fmt.Println(":-------Go WS Stunnel-------:")
	fmt.Println("")
	fmt.Println("Listening:", ListenAddr)
	fmt.Println("")
	fmt.Println(":---------------------------:")
	fmt.Println("")
}
