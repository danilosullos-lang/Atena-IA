import 'package:flutter/material.dart';

void main() => runApp(const AtenaDeliveryApp());

class MenuItem {
  final String name;
  final double price;
  const MenuItem(this.name, this.price);
}

class AtenaDeliveryApp extends StatefulWidget {
  const AtenaDeliveryApp({super.key});

  @override
  State<AtenaDeliveryApp> createState() => _AtenaDeliveryAppState();
}

class _AtenaDeliveryAppState extends State<AtenaDeliveryApp> {
  final items = const [
    MenuItem('Atena Smash', 29.90),
    MenuItem('Batata Suprema', 15.50),
    MenuItem('Refrigerante', 7.00),
  ];
  final cart = <MenuItem>[];

  double get total => cart.fold(4.99, (value, item) => value + item.price);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ATENA Delivery',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.deepOrange),
      home: Scaffold(
        appBar: AppBar(title: const Text('ATENA Delivery')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Atena Burgers', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
            const Text('Entrega estimada: 28 min • Taxa: R\$ 4,99'),
            const SizedBox(height: 16),
            ...items.map((item) => Card(
              child: ListTile(
                title: Text(item.name),
                subtitle: Text('R\$ ${item.price.toStringAsFixed(2)}'),
                trailing: FilledButton(
                  onPressed: () => setState(() => cart.add(item)),
                  child: const Text('Adicionar'),
                ),
              ),
            )),
            const SizedBox(height: 20),
            Text('Carrinho: ${cart.length} itens', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            Text('Total com entrega: R\$ ${total.toStringAsFixed(2)}'),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: cart.isEmpty ? null : () {},
              child: const Text('Fechar pedido'),
            ),
          ],
        ),
      ),
    );
  }
}
